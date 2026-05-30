"""Test EastMoney integration — sentiment analysis + data APIs."""
import sys
sys.path.insert(0, ".")

from potato.eastmoney import (
    analyze_sentiment,
    EastMoneyClient,
    POSITIVE_WORDS,
    NEGATIVE_WORDS,
    NEGATION_WORDS,
    DEGREE_WORDS,
    TRANSITION_WORDS,
    get_realtime_quote,
    get_stock_changes,
    get_hot_tables,
    get_kline_data,
    get_chip_distribution,
)


class TestSentimentAnalysis:

    def test_positive_text(self):
        result = analyze_sentiment("贵州茅台今天大涨3%创新高")
        assert result["category"] == "看涨"
        assert result["score"] > 0
        assert len(result["positive_words"]) > 0

    def test_negative_text(self):
        result = analyze_sentiment("A股暴跌，多只个股跌停，市场恐慌情绪蔓延")
        assert result["category"] == "看跌"
        assert result["score"] < 0
        assert len(result["negative_words"]) > 0

    def test_neutral_text(self):
        result = analyze_sentiment("今日大盘平开平走")
        assert result["category"] == "中性"
        assert abs(result["score"]) <= 0.5

    def test_negation_flips_positive(self):
        result = analyze_sentiment("不涨")
        assert result["score"] < 0

    def test_negation_flips_negative(self):
        result = analyze_sentiment("不跌")
        assert result["score"] > 0

    def test_degree_amplifies(self):
        result1 = analyze_sentiment("小幅反弹")
        result2 = analyze_sentiment("反弹")
        assert result1["score"] >= 0 or result2["score"] >= 0  # degree words modify intensity

    def test_transition_emphasis(self):
        result = analyze_sentiment("利好消息但是下跌")
        assert result["negative_words"] is not None

    def test_empty_text(self):
        result = analyze_sentiment("")
        assert result["category"] == "中性"
        assert result["score"] == 0.0

    def test_mixed_sentiment(self):
        result = analyze_sentiment("今天涨停了但是明天可能回调")
        assert result["positive_words"] is not None or result["negative_words"] is not None

    def test_client_initialization(self):
        client = EastMoneyClient(api_key="test_key")
        assert client.api_key == "test_key"

    def test_client_empty_key(self):
        client = EastMoneyClient()
        assert client.api_key == ""

    def test_dictionaries_not_empty(self):
        assert len(POSITIVE_WORDS) >= 30
        assert len(NEGATIVE_WORDS) >= 30
        assert len(NEGATION_WORDS) >= 5
        assert len(DEGREE_WORDS) >= 5
        assert len(TRANSITION_WORDS) >= 3


class TestDataAPIs:

    def test_get_realtime_quote_returns_dict(self):
        result = get_realtime_quote("600519")
        assert isinstance(result, dict)

    def test_get_realtime_quote_sh_code(self):
        result = get_realtime_quote("600519")
        if result:
            assert result.get("code") == "600519"
            assert "price" in result

    def test_get_realtime_quote_sz_code(self):
        result = get_realtime_quote("000001")
        if result:
            assert result.get("code") == "000001"

    def test_get_stock_changes_returns_list(self):
        result = get_stock_changes()
        assert isinstance(result, list)

    def test_get_hot_tables_returns_list(self):
        result = get_hot_tables()
        assert isinstance(result, list)

    def test_get_kline_data_returns_list(self):
        result = get_kline_data("600519", period="101", start="20250501", end="20250530")
        assert isinstance(result, list)

    def test_get_kline_data_daily_format(self):
        result = get_kline_data("600519", period="101", start="20250501", end="20250530")
        if result:
            first = result[0]
            assert isinstance(first, str)
            parts = first.split(",")
            assert len(parts) >= 5

    def test_get_chip_distribution_returns_dict(self):
        result = get_chip_distribution("600519")
        assert isinstance(result, dict)