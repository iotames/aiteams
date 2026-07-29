"""请求参数校验"""


def validate_required(data, fields):
    """检查必填字段"""
    missing = []
    for field in fields:
        if field not in data or (isinstance(data.get(field), str) and not data[field].strip()):
            missing.append(field)
    if missing:
        return False, f'缺少必填字段: {", ".join(missing)}'
    return True, None


def validate_positive_number(value, name='字段'):
    """验证正数"""
    try:
        v = float(value)
        if v < 0:
            return False, f'{name}不能为负数'
    except (TypeError, ValueError):
        return False, f'{name}必须为数字'
    return True, None
