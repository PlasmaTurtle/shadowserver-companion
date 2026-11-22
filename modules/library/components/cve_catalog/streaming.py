"""Read the vulnerabilities array a record at a time with bounded JSON buffering."""

import json
import re

from modules.workspace.components.aegis.json import strict_json_decoder

CHUNK = 128 * 1024
MAX_RECORD = 16 * 1024 * 1024


def records(path, cancel_event=None):
    from .transport import cancelled

    decoder = strict_json_decoder(max_bytes=MAX_RECORD)
    with path.open(encoding="utf-8") as stream:
        buffer = ""
        # The NVD envelope precedes its vulnerabilities array; reject arbitrary
        # envelopes rather than accidentally importing an unrelated JSON array.
        while True:
            cancelled(cancel_event)
            block = stream.read(CHUNK)
            if not block:
                raise ValueError("NVD feed has no vulnerabilities array")
            buffer += block
            match = re.search(r'"vulnerabilities"\s*:\s*\[', buffer)
            if match:
                buffer = buffer[match.end() :]
                break
            if len(buffer) > CHUNK * 2:
                raise ValueError("NVD feed envelope is too large")
        expect_value = True
        seen = False
        while True:
            cancelled(cancel_event)
            buffer = buffer.lstrip()
            if not buffer:
                buffer = stream.read(CHUNK)
                if not buffer:
                    raise ValueError("NVD feed ended before its array closed")
                continue
            if buffer.startswith("]"):
                if expect_value and seen:
                    raise ValueError("NVD feed has a trailing comma")
                tail = buffer[1:] + stream.read(CHUNK)
                # Published NVD JSON has this as its final envelope property.
                # Permit only the final object brace, never silent trailing junk.
                if tail.strip() != "}" or stream.read(1):
                    raise ValueError("NVD feed has an unexpected envelope suffix")
                return
            if not expect_value:
                if buffer[0] != ",":
                    raise ValueError("NVD feed has no record separator")
                buffer = buffer[1:]
                expect_value = True
                continue
            while True:
                try:
                    value, end = decoder.raw_decode(buffer)
                    break
                except RecursionError as error:
                    raise ValueError("NVD CVE record exceeds the JSON nesting limit") from error
                except json.JSONDecodeError as error:
                    if len(buffer) > MAX_RECORD:
                        raise ValueError("NVD CVE record exceeds the parsing limit") from error
                    more = stream.read(CHUNK)
                    if not more:
                        raise ValueError("NVD feed contains incomplete JSON") from error
                    buffer += more
            if (
                end > MAX_RECORD
                or not isinstance(value, dict)
                or not isinstance(value.get("cve"), dict)
            ):
                raise ValueError("NVD feed contains an invalid vulnerability")
            yield value["cve"]
            buffer = buffer[end:]
            expect_value = False
            seen = True
