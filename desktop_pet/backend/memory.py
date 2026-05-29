"""Episodic memory for desktop pet — categorized, persistent, no more amnesia.

Architecture:
    - Facts:     Persistent key-value knowledge about the user (name, preferences, etc.)
                 Stored in both user_facts.json (simple) AND memory_facts (DB, if available)
                 Organized by category: identity, preference, trading, personal, system, bytebot
    - Episodes:  Timestamped events with category + importance + tags
                 ChromaDB for vector search, DB for structured queries
                 HOT (0-15d) → WARM (15-30d) → compressed into summaries → EXPIRED (>30d, deleted)
    - Summaries: Compressed long-term recall from expired episodes

The AI system prompt uses build_memory_context() which injects:
    1. All known facts (categorized)
    2. Recent HOT episodes
    3. Related episodes (vector search on user input)
    4. WARM summaries (if relevant)
"""

import json
import logging
import os
import tempfile
import time
import uuid
import datetime
import random

_MEMORY_DIR = os.path.join(os.path.dirname(__file__), "memory_db")
_FACTS_PATH = os.path.join(os.path.dirname(__file__), "user_facts.json")

_chroma = None
_episodic_col = None

logger = logging.getLogger("potato.pet.memory")

FACT_CATEGORIES = {
    "identity": "身份信息（名字、年龄、职业等）",
    "preference": "偏好（喜欢的、不喜欢的、风格等）",
    "trading": "交易相关（平台、风险偏好、持仓偏好等）",
    "personal": "个人生活（家庭、日常、习惯等）",
    "system": "系统配置（密钥、平台、设置等）",
    "bytebot": "Bytebot 相关（远程桌面、任务偏好等）",
    "other": "其他信息",
}

EPISODE_CATEGORIES = {
    "conversation": "日常对话",
    "trading": "交易操作",
    "analysis": "分析讨论",
    "preference": "偏好表达",
    "personal": "个人信息",
    "system": "系统操作",
    "bytebot": "Bytebot 电脑操作",
    "reminder": "提醒事项",
    "other": "其他",
}


def _get_collection():
    global _chroma, _episodic_col
    if _episodic_col is not None:
        return _episodic_col
    try:
        import chromadb
        _chroma = chromadb.PersistentClient(path=_MEMORY_DIR)
        _episodic_col = _chroma.get_or_create_collection("episodes")
    except Exception as e:
        logger.warning("ChromaDB unavailable: %s", e)
        return None
    return _episodic_col


def _categorize_fact(key: str, value: str) -> str:
    """Auto-categorize a fact key into a semantic category."""
    k = key.upper()
    if any(w in k for w in ("NAME", "名字", "称呼", "NICKNAME")):
        return "identity"
    if any(w in k for w in ("RISK", "风险", "LEVEL", "TRADING", "交易", "平台", "PLATFORM",
                             "WATCHLIST", "自选", "PORTFOLIO", "持仓", "MARKET", "市场")):
        return "trading"
    if any(w in k for w in ("LIKE", "喜欢", "DISLIKE", "不喜欢", "PREF", "STYLE", "风格",
                             "LANGUAGE", "语言", "TOPIC", "主题")):
        return "preference"
    if any(w in k for w in ("FAMILY", "家人", "HOME", "家", "PET", "宠物", "BIRTHDAY", "生日",
                             "JOB", "工作", "AGE", "年龄", "GENDER", "性别")):
        return "personal"
    if any(w in k for w in ("BYTEBOT", "DESKTOP", "AGENT", "远程")):
        return "bytebot"
    if any(w in k for w in ("API_KEY", "KEY", "TOKEN", "SECRET", "URL", "ADDRESS",
                             "ACCOUNT", "PASSWORD")):
        return "system"
    return "other"


def _categorize_episode(text: str, ai_category: str = "") -> str:
    """Auto-categorize an episode based on content and AI-suggested category."""
    if ai_category in EPISODE_CATEGORIES:
        return ai_category
    t = text.lower()
    if any(w in t for w in ("股票", "行情", "交易", "买入", "卖出", "持仓", "分析", "板块", "涨停",
                             "stock", "trade", "buy", "sell", "portfolio", "market")):
        return "trading"
    if any(w in t for w in ("喜欢", "偏好", "不喜欢", "想要", "别这样", "风格",
                             "prefer", "like", "dislike", "style")):
        return "preference"
    if any(w in t for w in ("我叫", "我的名字", "我住", "我家", "我生日", "我工作",
                             "my name", "i live", "i work", "my job")):
        return "personal"
    if any(w in t for w in ("密钥", "平台", "设置", "key", "平台", "bytebot", "电脑操作",
                             "远程桌面", "desktop", "agent task")):
        return "system"
    if any(w in t for w in ("bytebot", "remote", "desktop", "computer task")):
        return "bytebot"
    if any(w in t for w in ("提醒", "记住", "别忘了", "important", "remind")):
        return "reminder"
    return "conversation"


class MemorySystem:
    """Categorized persistent memory — facts, episodes, summaries."""

    def __init__(self):
        self.facts = self._load_facts()
        self._db_memorystore = None

    def _get_db_memory(self):
        if self._db_memorystore is not None:
            return self._db_memorystore
        try:
            from potato.memory import MemoryStore
            from potato.config import load_settings
            self._db_memorystore = MemoryStore(settings=load_settings())
            return self._db_memorystore
        except Exception as e:
            logger.debug("MemoryStore DB unavailable: %s", e)
            return None

    def _load_facts(self):
        if os.path.exists(_FACTS_PATH):
            try:
                with open(_FACTS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        new_format = {}
                        for k, v in data.items():
                            if isinstance(v, dict) and "value" in v:
                                new_format[k] = v
                            else:
                                cat = _categorize_fact(k, str(v))
                                new_format[k] = {"value": str(v), "category": cat, "source": "user"}
                        return new_format
                    return {}
            except Exception as e:
                logger.warning("Failed to load facts: %s", e)
        return {}

    def _save_facts(self):
        try:
            os.makedirs(os.path.dirname(_FACTS_PATH), exist_ok=True)
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=os.path.dirname(_FACTS_PATH), suffix=".tmp", prefix="facts_"
            )
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(self.facts, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, _FACTS_PATH)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        except Exception as e:
            logger.warning("Failed to save facts: %s", e)

    def _sync_fact_to_db(self, key: str, value: str, category: str, source: str = "user"):
        """Sync a fact to the DB-backed MemoryStore if available."""
        db = self._get_db_memory()
        if db:
            try:
                db.set_fact(key, value, source=source, confidence=1.0)
            except Exception as e:
                logger.debug("DB fact sync failed: %s", e)

    def get_fact_context(self):
        if not self.facts:
            return "（暂无已知信息）"

        by_category = {}
        for k, v in self.facts.items():
            if isinstance(v, dict):
                cat = v.get("category", "other")
                val = v.get("value", "")
            else:
                cat = _categorize_fact(k, str(v))
                val = str(v)
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(f"{k}: {val}")

        lines = []
        cat_order = ["identity", "preference", "trading", "personal", "bytebot", "system", "other"]
        for cat in cat_order:
            if cat in by_category:
                cat_name = FACT_CATEGORIES.get(cat, cat)
                lines.append(f"【{cat_name}】")
                for item in by_category[cat]:
                    lines.append(f"  {item}")

        return "\n".join(lines) if lines else "（暂无已知信息）"

    def get_all_facts(self):
        result = {}
        for k, v in self.facts.items():
            if isinstance(v, dict):
                result[k] = v.get("value", "")
            else:
                result[k] = str(v)
        return result

    async def get_longmemory_context(self, user_text: str = None):
        col = _get_collection()
        if col is None:
            return ""

        memory_str = ""

        if user_text:
            try:
                from services import AIService
                query_vec = await AIService.get_embedding(user_text)
                if query_vec:
                    results = col.query(query_embeddings=[query_vec], n_results=5)
                    if results.get("documents") and results["documents"][0]:
                        now = datetime.datetime.now()
                        ranked = []
                        saw = set()
                        for doc, meta, dist in zip(
                            results["documents"][0],
                            results["metadatas"][0],
                            results["distances"][0],
                        ):
                            content_hash = hash(doc[:100])
                            if content_hash in saw:
                                continue
                            saw.add(content_hash)
                            base_score = 1 / (1 + dist)
                            date_str = meta.get("date", "1970-01-01")
                            cat = meta.get("category", "conversation")
                            try:
                                days = (now - datetime.datetime.strptime(date_str, "%Y-%m-%d")).days
                            except Exception:
                                days = 9999
                            boost = 1.5 if days <= 3 else 1.2 if days <= 15 else 1.0
                            ranked.append({"content": doc, "date": date_str, "category": cat, "score": base_score * boost})
                        ranked.sort(key=lambda x: x["score"], reverse=True)
                        if ranked:
                            memory_str += "\n【关联往事】\n"
                            for m in ranked[:5]:
                                cat_name = EPISODE_CATEGORIES.get(m["category"], m["category"])
                                memory_str += f"  - [{cat_name}] ({m['date']}) {m['content'][:200]}\n"
            except Exception as e:
                logger.warning("Memory search error: %s", e)
        else:
            try:
                total = col.count()
                if total > 0:
                    offset = random.randint(0, total - 1)
                    rnd = col.get(limit=1, offset=offset)
                    if rnd.get("documents"):
                        doc = rnd["documents"][0]
                        meta = rnd["metadatas"][0] if rnd.get("metadatas") else {}
                        date_str = meta.get("date", "久远的回忆")
                        cat = meta.get("category", "")
                        cat_name = EPISODE_CATEGORIES.get(cat, cat)
                        memory_str += f"\n【突然想起】\n- [{cat_name}] ({date_str}) {doc}\n"
            except Exception as e:
                logger.warning("Random memory recall failed: %s", e)

        db = self._get_db_memory()
        if db:
            try:
                summaries = db.get_recent_summaries(limit=2)
                if summaries:
                    memory_str += "\n【历史摘要】\n"
                    for s in summaries:
                        s_dict = dict(s) if isinstance(s, dict) else {}
                        memory_str += f"  - [{s_dict.get('period_start', '')}~{s_dict.get('period_end', '')}] {s_dict.get('summary', '')[:200]}\n"
            except Exception as e:
                logger.debug("Summary recall failed: %s", e)

        return memory_str

    async def execute_updates(self, update_instruction: dict):
        new_facts = update_instruction.get("new_facts")
        if new_facts and isinstance(new_facts, dict):
            logger.info("Update facts: %s", new_facts)
            for k, v in new_facts.items():
                cat = _categorize_fact(k, str(v))
                self.facts[k] = {"value": str(v), "category": cat, "source": "ai_extracted"}
                self._sync_fact_to_db(k, str(v), cat, source="ai_extracted")
            self._save_facts()

        new_episode = update_instruction.get("new_episode")
        if new_episode:
            col = _get_collection()
            if col is None:
                logger.warning("ChromaDB not available, episode skipped")
                return
            try:
                from services import AIService
                vector = await AIService.get_embedding(new_episode)
                importance = update_instruction.get("importance", 5)
                ai_category = update_instruction.get("category", "conversation")
                category = _categorize_episode(new_episode, ai_category)
                tags = update_instruction.get("tags", [])
                if isinstance(tags, str):
                    tags = [tags]

                ep_id = str(uuid.uuid4())
                now_date = datetime.datetime.now().strftime("%Y-%m-%d")
                metadata = {
                    "timestamp": time.time(),
                    "date": now_date,
                    "category": category,
                    "importance": importance,
                    "tags": json.dumps(tags) if tags else "[]",
                }
                doc_text = new_episode if len(new_episode) <= 500 else new_episode[:500]
                if vector:
                    col.add(
                        documents=[doc_text],
                        embeddings=[vector],
                        metadatas=[metadata],
                        ids=[ep_id],
                    )
                else:
                    col.add(
                        documents=[doc_text],
                        metadatas=[metadata],
                        ids=[ep_id],
                    )

                logger.info("Episode stored [%s] importance=%d total=%d", category, importance, col.count())

                db = self._get_db_memory()
                if db:
                    try:
                        db.store_episode(new_episode, category=category,
                                         importance=importance, tags=tags)
                    except Exception as e:
                        logger.debug("DB episode sync failed: %s", e)
            except Exception as e:
                logger.error("Episode store error: %s", e)

    def cleanup_expired(self, max_days: int = 30):
        col = _get_collection()
        if col is None:
            return {"expired_deleted": 0}
        deleted = 0
        try:
            cutoff = (datetime.datetime.now() - datetime.timedelta(days=max_days)).strftime("%Y-%m-%d")
            all_data = col.get(include=["metadatas"])
            ids_to_remove = []
            for i, meta in enumerate(all_data.get("metadatas", [])):
                if meta.get("date", "9999") < cutoff:
                    ids_to_remove.append(all_data["ids"][i])
            if ids_to_remove:
                col.delete(ids=ids_to_remove)
                deleted = len(ids_to_remove)
        except Exception as e:
            logger.warning("ChromaDB cleanup error: %s", e)

        db = self._get_db_memory()
        if db:
            try:
                db_result = db.cleanup_expired()
                deleted += db_result.get("expired_deleted", 0)
            except Exception as e:
                logger.debug("DB cleanup sync failed: %s", e)

        return {"expired_deleted": deleted}

    def search_memories(self, keyword: str, limit: int = 10):
        results = []
        facts_matching = {}
        for k, v in self.facts.items():
            val = v.get("value", str(v)) if isinstance(v, dict) else str(v)
            if keyword.lower() in k.lower() or keyword.lower() in val.lower():
                facts_matching[k] = val
        if facts_matching:
            results.append({"type": "fact", "data": facts_matching})

        col = _get_collection()
        if col is not None:
            try:
                chroma_results = col.query(query_texts=[keyword], n_results=limit,
                                           include=["documents", "metadatas"])
                docs = chroma_results.get("documents", [[]])[0]
                metas = chroma_results.get("metadatas", [[]])[0]
                for doc, meta in zip(docs, metas):
                    cat = meta.get("category", "")
                    results.append({
                        "type": "episode",
                        "content": doc,
                        "date": meta.get("date", ""),
                        "category": cat,
                        "category_name": EPISODE_CATEGORIES.get(cat, cat),
                    })
            except Exception:
                pass

        db = self._get_db_memory()
        if db:
            try:
                db_results = db.search_memories(keyword, limit=5)
                for r in db_results:
                    r_dict = dict(r) if isinstance(r, dict) else {}
                    results.append({"type": "db_episode", **r_dict})
            except Exception:
                pass

        return results

    def get_hot_memories(self, limit: int = 10):
        col = _get_collection()
        if col is None:
            return []
        try:
            total = col.count()
            if total == 0:
                return []
            n = min(limit, total)
            data = col.get(limit=n, include=["documents", "metadatas"])
            result = []
            for d, m in zip(data.get("documents", []), data.get("metadatas", [])):
                result.append({
                    "content": d,
                    "date": m.get("date", ""),
                    "category": m.get("category", ""),
                    "category_name": EPISODE_CATEGORIES.get(m.get("category", ""), ""),
                })
            return result
        except Exception:
            return []

    def get_recent_summaries(self, limit: int = 3):
        db = self._get_db_memory()
        if db:
            try:
                return db.get_recent_summaries(limit=limit)
            except Exception:
                pass
        return self.get_hot_memories(limit=limit)

    def build_memory_context(self, user_input: str = ""):
        facts_str = self.get_fact_context()
        return f"已知用户信息: {facts_str}"

    def store_fact_direct(self, key: str, value: str, category: str = None, source: str = "user"):
        """Directly store/update a fact with category."""
        cat = category or _categorize_fact(key, value)
        self.facts[key] = {"value": value, "category": cat, "source": source}
        self._save_facts()
        self._sync_fact_to_db(key, value, cat, source)
        logger.info("Direct fact store: %s [%s] = %s", key, cat, value[:50])

    def delete_fact(self, key: str):
        """Delete a fact by key."""
        if key in self.facts:
            del self.facts[key]
            self._save_facts()
            logger.info("Fact deleted: %s", key)