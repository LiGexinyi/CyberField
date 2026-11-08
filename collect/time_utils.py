"""统一时间：秒/毫秒时间戳和带时区日期转为北京时间；未知时间留空。"""
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

BEIJING = timezone(timedelta(hours=8))

def normalize_time(raw):
    """返回固定格式的北京时间，不把年份或不完整日期补造成具体日期。"""
    value = str(raw or "").strip()
    if not value:
        return ""
    try:
        if re.fullmatch(r"[+-]?\d{10}(?:\.\d+)?|[+-]?\d{13}", value):
            stamp = float(value)
            if len(value.lstrip("+-")) == 13:
                stamp /= 1000
            dt = datetime.fromtimestamp(stamp, timezone.utc)
        elif re.match(r"^\d{4}-\d{2}-\d{2}(?:$|[ T])", value):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=BEIJING)
        return dt.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OverflowError, OSError):
        return ""
