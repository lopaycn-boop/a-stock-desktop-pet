"""PlanExecute multi-step analysis — 小土豆计划-执行分析引擎.

Instead of a single LLM call for analysis, PlanExecute:
1. PLAN: LLM creates a structured analysis plan (what data to gather, what to evaluate)
2. EXECUTE: Each plan step is executed sequentially with data enrichment
3. SYNTHESIZE: All step results are combined into a final trading decision

This produces higher-quality analysis because:
- Each step has focused context and can use specialized tools
- EastMoney real-time data feeds into individual steps
- The final synthesis has richer inputs than a single-pass approach
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from potato.config import load_settings
from potato.llm import achat
from potato.eastmoney import (
    EastMoneyClient,
    analyze_sentiment,
    get_stock_changes,
    get_hot_tables,
    get_realtime_quote as em_get_realtime_quote,
)
from potato.iwencai import IwencaiClient, format_iwencai_to_text

logger = logging.getLogger("potato.trading.plan_execute")


async def create_analysis_plan(
    symbols: list[str],
    user_prefs: dict[str, Any] | None = None,
    news_items: list[dict] | None = None,
    em_context: str = "",
    sentiment_block: str = "",
) -> dict[str, Any]:
    """Step 1: LLM creates a structured analysis plan for the given stocks."""
    prefs = user_prefs or {}
    risk_level = prefs.get("risk_level", "conservative")
    watchlist = prefs.get("watchlist", [])
    sectors = prefs.get("sectors", [])

    iw_block = ""
    try:
        iw = IwencaiClient()
        queries = [f"{s}最新行情" for s in symbols[:3]]
        if sectors:
            queries.insert(0, f"属于{sectors[0]}板块的强势股")
        for q in queries[:2]:
            result = await asyncio.to_thread(iw.select_stocks, q, limit=3)
            if result.get("ok") and result.get("stocks"):
                names = [f"{s.get('name','?')}({s.get('code','?')})" for s in result["stocks"][:3]]
                iw_block += f"\n问财筛选「{q}」: {', '.join(names)}"
    except Exception:
        pass

    prompt = f"""你是专业操盘分析师。根据以下信息，制定一个详细的分析计划。

股票: {', '.join(symbols)}
风险偏好: {risk_level}
自选股: {', '.join(watchlist) or '未设置'}
关注板块: {', '.join(sectors) or '未设置'}
{em_context}{sentiment_block}{iw_block}

请输出JSON格式的分析计划：
{{
    "plan_id": "唯一ID",
    "overall_thesis": "50字市场大判断",
    "steps": [
        {{
            "step_id": 1,
            "type": "sentiment|technical|fundamental|catalyst|risk",
            "target_symbol": "股票代码",
            "question": "这个步骤要回答什么问题",
            "data_needs": ["realtime_quote", "stock_changes", "sentiment", "hot_tables"],
            "priority": 1-5
        }}
    ],
    "max_steps": 5,
    "focus_areas": ["重点分析领域1", "领域2"]
}}

规则：
1. 最多5个步骤，每个步骤聚焦一个方面
2. type必须是: sentiment(情绪), technical(技术面), fundamental(基本面), catalyst(催化剂), risk(风险)
3. data_needs指定需要什么数据支持
4. priority越高越先执行
5. 根据当前市场环境（牛市/熊市/震荡）调整重点"""

    settings = load_settings()
    result = await achat(
        prompt,
        system="你是专业量化操盘规划师，制定严谨的分析计划。只输出JSON。",
        settings=settings,
        max_tokens=1500,
        task="analysis",
    )

    if result.get("ok"):
        try:
            plan = json.loads(result["content"])
            plan["plan_id"] = plan.get("plan_id", f"plan-{uuid.uuid4().hex[:8]}")
            plan["created_at"] = datetime.now(timezone.utc).isoformat()
            return {"ok": True, "plan": plan}
        except json.JSONDecodeError:
            return {"ok": True, "plan_text": result["content"]}
    return {"ok": False, "error": result.get("error", "Plan creation failed")}


async def execute_plan_step(
    step: dict[str, Any],
    symbols: list[str],
    all_step_results: list[dict[str, Any]],
    news_items: list[dict] | None = None,
    em_context: str = "",
    sentiment_block: str = "",
) -> dict[str, Any]:
    """Step 2: Execute a single analysis step with enriched data."""
    step_type = step.get("type", "technical")
    target = step.get("target_symbol", symbols[0] if symbols else "000001")
    question = step.get("question", "")
    data_needs = step.get("data_needs", [])

    step_data = {}

    if "realtime_quote" in data_needs:
        for sym in symbols[:5]:
            try:
                q = await asyncio.to_thread(em_get_realtime_quote, sym)
                if q and q.get("name"):
                    step_data[f"quote_{sym}"] = f"{q['name']}({sym}): ¥{q.get('price', 'N/A')} {q.get('change_pct', 0):+.2f}%"
            except Exception:
                pass

    if "stock_changes" in data_needs:
        try:
            changes = await asyncio.to_thread(get_stock_changes)
            if changes:
                top = changes[:5]
                step_data["anomalies"] = "; ".join(f"{c.get('name','?')}({c.get('code','?')}): {c.get('type','?')}" for c in top)
        except Exception:
            pass

    if "hot_tables" in data_needs:
        try:
            tables = await asyncio.to_thread(get_hot_tables)
            if tables:
                step_data["dragon_tiger"] = f"{len(tables)} stocks on Dragon Tiger List"
        except Exception:
            pass

    if "sentiment" in data_needs and sentiment_block:
        step_data["sentiment"] = sentiment_block

    previous_context = ""
    if all_step_results:
        previous_context = "\n\n已完成的分析步骤:\n"
        for r in all_step_results:
            previous_context += f"- [{r.get('step_type', '?')}] {r.get('summary', '')}\n"

    news_block = ""
    if news_items and "sentiment" in data_needs:
        news_block = "\n最新资讯:\n" + "\n".join(f"- {n.get('title', '')}" for n in news_items[:8])

    prompt = f"""分析步骤: {step_type}
目标股票: {target}
需要回答的问题: {question}

实时数据:
{chr(10).join(f'- {k}: {v}' for k, v in step_data.items()) if step_data else '暂无实时数据'}
{em_context}
{news_block}
{previous_context}

请输出JSON格式的分析结果：
{{
    "step_id": {step.get('step_id', 1)},
    "step_type": "{step_type}",
    "target_symbol": "{target}",
    "findings": "50字核心发现",
    "evidence": ["证据1", "证据2", "证据3"],
    "confidence": 0.0-1.0,
    "summary": "100字详细分析",
    "recommendation": "看涨/看跌/观望",
    "risk_flags": ["风险点1", "风险点2"]
}}"""

    settings = load_settings()
    result = await achat(
        prompt,
        system="你是专业操盘分析师，执行分析步骤只输出JSON。每一步必须有具体发现和证据。",
        settings=settings,
        max_tokens=1200,
        task="analysis",
    )

    if result.get("ok"):
        try:
            step_result = json.loads(result["content"])
            step_result["step_id"] = step.get("step_id", 1)
            step_result["step_type"] = step_type
            step_result["target_symbol"] = target
            return {"ok": True, "step_result": step_result}
        except json.JSONDecodeError:
            return {
                "ok": True,
                "step_result": {
                    "step_id": step.get("step_id", 1),
                    "step_type": step_type,
                    "target_symbol": target,
                    "findings": result["content"][:200],
                    "confidence": 0.5,
                    "summary": result["content"][:300],
                    "recommendation": "观望",
                    "risk_flags": [],
                },
            }
    return {"ok": False, "error": result.get("error", "Step execution failed")}


async def synthesize_plan(
    plan: dict[str, Any],
    step_results: list[dict[str, Any]],
    symbols: list[str],
    user_prefs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Step 3: Synthesize all step results into a final trading decision."""
    prefs = user_prefs or {}
    risk_level = prefs.get("risk_level", "conservative")

    step_summaries = []
    for sr in step_results:
        r = sr.get("step_result", sr)
        step_summaries.append({
            "type": r.get("step_type", "?"),
            "target": r.get("target_symbol", "?"),
            "findings": r.get("findings", ""),
            "confidence": r.get("confidence", 0),
            "recommendation": r.get("recommendation", "观望"),
            "risk_flags": r.get("risk_flags", []),
        })

    prompt = f"""你已完成多步分析，现在综合所有步骤结果做出最终操盘决策。

市场大判断: {plan.get('overall_thesis', '未确定')}
风险偏好: {risk_level}
分析步骤结果:
{json.dumps(step_summaries, ensure_ascii=False, indent=2)}

请输出最终交易决策JSON：
{{
    "market_summary": "200字市场判断（综合所有步骤发现）",
    "market_regime": "bull/bear/sideways/volatile",
    "stock_picks": [
        {{
            "symbol": "代码",
            "name": "名称",
            "action": "BUY/SELL/HOLD/WATCH",
            "confidence": 0.0-1.0,
            "reasoning": "综合多步分析的3句话理由：技术面+基本面+消息面",
            "why_not_others": "为什么不是同板块其他股",
            "entry_price": "建议买入价",
            "target_price": "目标价",
            "stop_loss": "止损价（必须设）",
            "position_size": "仓位百分比1-100%",
            "time_horizon": "短线/中线/长线",
            "risk_reward": "风险收益比",
            "news_correlation": "与哪条消息相关",
            "catalysts": ["催化剂1", "催化剂2"],
            "risks": ["风险1", "风险2"],
            "monitor_signals": {{
                "add_conditions": "加仓条件",
                "exit_conditions": "卖出条件",
                "red_flags": "必须离场信号"
            }}
        }}
    ],
    "risk_warnings": ["系统性风险1", "风险2"],
    "action_plan": "简洁操作建议",
    "position_sizing": {{
        "max_single_pct": 30,
        "recommended_cash_reserve_pct": 20,
        "reasoning": "仓位逻辑"
    }},
    "sell_strategy": {{
        "take_profit_rules": "分批止盈规则",
        "stop_loss_rules": "止损规则",
        "trailing_stop": "移动止损策略"
    }},
    "plan_evidence": {{
        "steps_completed": {len(step_results)},
        "confidence_weighted_avg": 0.0,
        "key_findings": ["发现1", "发现2"]
    }}
}}

规则：
1. stock_picks最多5只
2. confidence < 0.65不做BUY推荐
3. 每只必须设止损价
4. 必须综合多步分析的发现，不能只依赖单一步骤
5. 保守策略下仓位不超30%"""

    settings = load_settings()
    result = await achat(
        prompt,
        system="你是专业量化操盘手，综合多步分析做出最终决策。只输出JSON。",
        settings=settings,
        max_tokens=4000,
        task="analysis",
    )

    if result.get("ok"):
        try:
            analysis = json.loads(result["content"])
            analysis["_metadata"] = {
                "run_id": f"plan-execute-{uuid.uuid4().hex[:8]}",
                "method": "plan_execute",
                "steps_completed": len(step_results),
                "symbols_analyzed": symbols,
                "model": result.get("model"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            return {"ok": True, "analysis": analysis}
        except json.JSONDecodeError:
            return {"ok": True, "analysis_text": result["content"]}
    return {"ok": False, "error": result.get("error", "Synthesis failed")}


async def run_plan_execute_analysis(
    symbols: list[str],
    user_prefs: dict[str, Any] | None = None,
    news_items: list[dict] | None = None,
    em_context: str = "",
    sentiment_block: str = "",
) -> dict[str, Any]:
    """Full PlanExecute pipeline: Plan → Execute each step → Synthesize.

    This is the main entry point. Call from scheduler or manual analysis.
    """
    logger.info("PlanExecute: Starting plan-create-execute-synthesize for %s", symbols)

    # Step 1: Create plan
    plan_result = await create_analysis_plan(
        symbols=symbols,
        user_prefs=user_prefs,
        news_items=news_items,
        em_context=em_context,
        sentiment_block=sentiment_block,
    )

    if not plan_result.get("ok"):
        logger.warning("PlanExecute: Plan creation failed: %s", plan_result.get("error"))
        return plan_result

    plan = plan_result.get("plan", {})
    if not plan.get("steps"):
        logger.warning("PlanExecute: No steps in plan, falling back to plan_text")
        plan = {"overall_thesis": plan_result.get("plan_text", "市场分析"), "steps": [
            {"step_id": 1, "type": "technical", "target_symbol": symbols[0] if symbols else "000001",
             "question": "综合技术面分析", "data_needs": ["realtime_quote"], "priority": 1}
        ]}

    logger.info("PlanExecute: Plan created with %d steps", len(plan.get("steps", [])))

    # Step 2: Execute each step
    step_results = []
    steps = sorted(plan.get("steps", []), key=lambda s: s.get("priority", 5))

    for step in steps[:5]:
        step_result = await execute_plan_step(
            step=step,
            symbols=symbols,
            all_step_results=step_results,
            news_items=news_items,
            em_context=em_context,
            sentiment_block=sentiment_block,
        )
        if step_result.get("ok"):
            step_results.append(step_result)
            logger.info("PlanExecute: Step %d (%s) completed", step.get("step_id", 0), step.get("type", "?"))
        else:
            logger.warning("PlanExecute: Step %d failed: %s", step.get("step_id", 0), step_result.get("error"))

    if not step_results:
        return {"ok": False, "error": "All plan steps failed"}

    # Step 3: Synthesize
    synthesis = await synthesize_plan(
        plan=plan,
        step_results=step_results,
        symbols=symbols,
        user_prefs=user_prefs,
    )

    if synthesis.get("ok"):
        synthesis["plan"] = plan
        synthesis["step_results"] = step_results

    logger.info("PlanExecute: Complete. Steps=%d, ok=%s", len(step_results), synthesis.get("ok"))
    return synthesis