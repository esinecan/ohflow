"""Parse a small config format: one `key = value` per line, and `#` starts a comment."""

SCHEMA = {"name": str, "port": int, "debug": bool, "workers": int}

TRUE = ("true", "yes", "on")
FALSE = ("false", "no", "off")


class ConfigError(ValueError):
    def __init__(self, message, line):
        super().__init__(f"line {line}: {message}")
        self.line = line


def _convert(kind, raw, line):
    if kind is bool:
        if raw.lower() in TRUE:
            return True
        if raw.lower() in FALSE:
            return False
        raise ConfigError(f"expected true or false, got {raw!r}", line)
    if kind is int:
        try:
            return int(raw)
        except ValueError:
            raise ConfigError(f"expected a whole number, got {raw!r}", line) from None
    return raw


def parse(text, schema=SCHEMA):
    config = {}
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.split("#", 1)[0].strip()
        if not stripped:
            continue
        key, sep, value = stripped.partition("=")
        if not sep:
            raise ConfigError(f"expected key = value, got {stripped!r}", number)
        key, value = key.strip(), value.strip()
        config[key] = _convert(schema.get(key, str), value, number)
    return config
