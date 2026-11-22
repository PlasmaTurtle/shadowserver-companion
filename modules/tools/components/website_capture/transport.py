"""HTTP(S) URL normalization for capture callers; Chromium owns all transport."""

from urllib.parse import quote, urlsplit, urlunsplit

import idna


def web_url(value):
    """Normalize a browser destination without resolving or restricting its host."""
    if (
        not isinstance(value, str)
        or not value.strip()
        or "\\" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError("Invalid website URL")
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("A complete HTTP or HTTPS website URL is required")
        host = parsed.hostname
        port = parsed.port
        if ":" in host:
            host = f"[{host}]"
        elif not host.isascii():
            host = idna.encode(host, uts46=True).decode("ascii")
        authority = host.lower()
        if port is not None and port != (443 if parsed.scheme == "https" else 80):
            authority += f":{port}"
        if parsed.username is not None:
            userinfo = quote(parsed.username, safe="%!$&'()*+,;=-._~")
            if parsed.password is not None:
                userinfo += ":" + quote(parsed.password, safe="%!$&'()*+,;=:-._~")
            authority = userinfo + "@" + authority
        normalized = urlunsplit(
            (
                parsed.scheme,
                authority,
                quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~"),
                "",
                "",
            )
        )
        if "?" in value.split("#", 1)[0]:
            normalized += "?" + quote(parsed.query, safe="%/?@:!$&'()*+,;=-._~")
        if "#" in value:
            normalized += "#" + quote(parsed.fragment, safe="%/?@:!$&'()*+,;=-._~")
        return normalized
    except (UnicodeError, ValueError) as error:
        raise ValueError(str(error)) from None
