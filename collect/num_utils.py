"""互动数文本解析：全项目共用一份，避免各模块口径漂移。

支持 int/float、含逗号字符串、"万"/"亿" 后缀；解析失败一律返回 0，
绝不抛错中断采集或搜索流程（互动数只用于排序/筛选，不是关键字段）。
"""


def parse_count(value) -> float:
    """把互动数转成可比较数字；布尔、空值、非法文本按 0 处理。"""
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return 0.0
    text = value.strip().replace(",", "")
    if not text:
        return 0.0
    multiplier = 1.0
    if text.endswith("亿"):
        multiplier, text = 100000000.0, text[:-1]
    elif text.endswith("万"):
        multiplier, text = 10000.0, text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return 0.0


def parse_count_int(value) -> int:
    """整数版：评论点赞等只需要整数的场景。"""
    return int(parse_count(value))
