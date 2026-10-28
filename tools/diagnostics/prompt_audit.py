#!/usr/bin/env python3
"""Render a complete saved IFC request as an offline, source-linked reading view.

Only presentation changes: no model calls, schema expansion, omitted fields or
production imports. Unknown fields remain visible. The original bytes are embedded
for download; character counts are not token or billing estimates.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
import sys

LABELS = {
    "priorityHeader": "Приоритеты и инструкции", "runtimeProgramInvariants": "Правила runtime",
    "runtimeCapabilityContract": "Каталог возможностей", "capabilities": "Возможности",
    "requiredJsonShape": "Форма ответа", "schemaDefinitions": "Общие определения схемы",
    "parents": "Исходные предметы", "parentFactsReadOnly": "Факты о родителях",
    "balanceCorridor": "Числовые ориентиры баланса", "sourceWireUnits": "Единицы исходных данных",
    "fieldGuide": "Правила чтения каталога", "params": "Параметры", "properties": "Поля",
    "required": "Обязательные поля", "enum": "Допустимые значения", "default": "Значение по умолчанию",
    "neutral": "Нейтральное значение", "type": "Тип", "description": "Описание",
    "minimum": "Минимум (включительно)", "maximum": "Максимум (включительно)",
    "exclusiveMinimum": "Строго больше", "exclusiveMaximum": "Строго меньше",
    "additionalProperties": "Дополнительные поля", "anyOf": "Хотя бы один вариант",
    "oneOf": "Ровно один вариант", "allOf": "Все условия вместе", "$defs": "Общие определения",
    "$ref": "Ссылка на определение", "items": "Элементы массива", "const": "Точное значение",
    "response_format": "Формат ответа провайдеру", "messages": "Сообщения по порядку",
    "instructions": "Системные инструкции", "input": "Вход провайдера Responses",
    "does": "Что делает", "meaning": "Смысл параметра", "requires": "Условия применения",
    "kind": "Вид условия / сущности", "message": "Пояснение условия",
    "min": "Минимум", "max": "Максимум", "multipleOf": "Кратно", "pattern": "Шаблон значения",
    "shape": "Вложенная форма", "reference": "Правила ссылки на сущность", "targetKinds": "Разрешённые типы целей",
    "allowSelf": "Разрешена ссылка на себя", "graphEdge": "Связь графа", "optional": "Разрешён пропуск",
    "omissionAllowedOnlyWhen": "Условие разрешённого пропуска", "units": "Единицы измерения",
    "consumerConstraint": "Ограничение потребителя", "projectionConstraints": "Ограничения преобразования",
    "evidence": "Контекст захвата (не обязательно отправлен модели)",
}


def strict_json(text):
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError(f"Duplicate JSON member: {key!r}")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"Non-JSON number: {value}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def pointer(parent, key):
    return parent + "/" + str(key).replace("~", "~0").replace("/", "~1")


def anchor(path):
    return "p-" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:20]


def label(key, value):
    title = LABELS.get(str(key), str(key))
    if title != str(key):
        title += f" · {key}"
    if isinstance(value, dict):
        identity = value.get("fn") or value.get("name") or value.get("role")
        if isinstance(identity, str):
            title += " — " + identity
    return title


def decode_content(key, value):
    # Only JSON containers in message/body text get a second, explicitly marked
    # view. Arbitrary prose and malformed/duplicate-member JSON stay verbatim.
    if key in {"content", "text", "body"} and isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            result = strict_json(value)
            if isinstance(result, (dict, list)):
                return result
        except (ValueError, RecursionError):
            pass
    return None


def scalar(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, allow_nan=False)


def scalar_type(value):
    if value is None:
        return "null"
    return {str: "текст", bool: "boolean", int: "integer", float: "number"}[type(value)]


def serialized_chars(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False))


def iter_children(value):
    return value.items() if isinstance(value, dict) else enumerate(value)


def render_node(key, value, path, depth, markdown, leaves, refs):
    title = label(key, value)
    escaped_title, escaped_path = html.escape(title), html.escape(path or "/")
    node_id = anchor(path)
    decoded = decode_content(str(key), value)
    view = decoded if decoded is not None else value
    note = " · JSON внутри строки; путь после :: относится к декодированному JSON" if decoded is not None else ""
    markdown.append("  " * depth + "- " + title.replace("\n", " ") + f" [{path or '/'}]" + note)
    source = f'<a class="source" href="#{node_id}" title="Путь к исходному значению">{escaped_path}</a>'
    if isinstance(view, (dict, list)):
        children = []
        child_base = path + "::" if decoded is not None else path
        for child_key, child in iter_children(view):
            children.append(render_node(str(child_key), child, pointer(child_base, child_key), depth + 1, markdown, leaves, refs))
        if not view:
            markdown.append("  " * (depth + 1) + ("{}" if isinstance(view, dict) else "[]"))
        kind = "объект" if isinstance(view, dict) else "массив"
        return (f'<details class="node" id="{node_id}"' + (" open" if depth < 2 else "") + '>'
                f'<summary>{escaped_title} <small>{kind}, {len(view)}; {serialized_chars(value):,} симв.</small></summary>'
                f'<div class="node-body">{source}<small>{html.escape(note)}</small>' + "".join(children) + '</div></details>')
    text = scalar(value)
    reference = ""
    if key == "$ref" and isinstance(value, str):
        targets = refs.get(value, [])
        if len(targets) == 1:
            reference = source_link(targets[0], "Открыть определение")
        else:
            reference = '<small>Ссылка не разрешена однозначно в этом файле; значение сохранено.</small>'
    # No truncation; indentation separates prose from structure in the text export.
    markdown.extend("  " * (depth + 1) + "| " + line for line in text.split("\n"))
    leaves.append((path, value))
    return (f'<div class="leaf" id="{node_id}"><div class="field">{escaped_title} '
            f'<small>{scalar_type(value)}</small></div>{source}<div class="value">{html.escape(text)}</div>{reference}</div>')


def source_link(path, caption="Исходные поля"):
    return f'<a href="#{anchor(path)}">{html.escape(caption)}</a>'


def prose(value):
    """Literal prose and structured field documentation, never a JSON blob."""
    if isinstance(value, dict):
        if not value:
            return '<span class="empty">Пустой объект</span>'
        rows = []
        for key, child in value.items():
            title = html.escape(LABELS.get(key, key))
            if LABELS.get(key, key) != key:
                title += ' <small>' + html.escape(key) + '</small>'
            rows.append('<dt>' + title + '</dt><dd>' + prose(child) + '</dd>')
        return '<dl class="structured">' + ''.join(rows) + '</dl>'
    if isinstance(value, list):
        if not value:
            return '<span class="empty">Пустой список</span>'
        return '<ol>' + ''.join('<li>' + prose(child) + '</li>' for child in value) + '</ol>'
    return html.escape(scalar(value))


def compact_words(value):
    if isinstance(value, list):
        return ', '.join(compact_words(child) for child in value) or 'пустой список'
    if isinstance(value, dict):
        return '; '.join(f'{key}: {compact_words(child)}' for key, child in value.items()) or 'пустой объект'
    return scalar(value)


def documents(value, path=""):
    """Walk exact source paths; never merge messages or expand references."""
    if isinstance(value, (dict, list)):
        yield path, value
        for key, child in iter_children(value):
            child_path = pointer(path, key)
            decoded = decode_content(str(key), child)
            if decoded is not None:
                yield from documents(decoded, child_path + "::")
            elif isinstance(child, (dict, list)):
                yield from documents(child, child_path)


def param_sentence(card):
    pieces = ["Необязателен" if card.get("optional") is True else "Обязателен"]
    names = {"type": "тип", "typeRef": "тип по ссылке", "enum": "выбор только из", "const": "ровно",
             "minimum": "не меньше", "maximum": "не больше", "min": "не меньше", "max": "не больше",
             "multipleOf": "кратно", "pattern": "шаблон", "exclusiveMinimum": "строго больше",
             "exclusiveMaximum": "строго меньше", "units": "единицы", "default": "объявленный default",
             "neutral": "нейтральное значение", "omissionAllowedOnlyWhen": "пропуск допустим только при"}
    for key, title in names.items():
        if key in card:
            pieces.append(title + ": " + compact_words(card[key]))
    return "; ".join(pieces) + "."


def param_documentation(fn, name, param, guide, by_fn, path):
    if isinstance(param.get("meaning"), str):
        return param["meaning"], None, "direct"
    types = guide.get("types", {})
    if isinstance(param.get("typeRef"), str) and isinstance(types, dict):
        shape = types.get(param["typeRef"])
        if isinstance(shape, dict) and isinstance(shape.get("description"), str):
            return shape["description"], pointer(pointer(pointer(path, "fieldGuide"), "types"), param["typeRef"]), "typeRef"
    inheritance = "configure_armor params without meaning inherit exact meaning from configure_accessory params of the same name; all own bounds and units still apply."
    if fn == "configure_armor" and guide.get("armorParamInheritance") == inheritance:
        accessory, ap = by_fn.get("configure_accessory", ({}, ""))
        params = accessory.get("params", {})
        inherited = params.get(name) if isinstance(params, dict) else None
        if isinstance(inherited, dict) and isinstance(inherited.get("meaning"), str):
            return inherited["meaning"], pointer(pointer(ap, "params"), name), "armorParamInheritance"
    return None, None, "missing"


def capability_cards(catalog, path):
    capabilities = catalog.get("capabilities", [])
    if not isinstance(capabilities, list):
        return ""
    by_fn = {card.get("fn"): (card, pointer(pointer(path, "capabilities"), i))
             for i, card in enumerate(capabilities) if isinstance(card, dict) and isinstance(card.get("fn"), str)}
    guide = catalog.get("fieldGuide", {})
    guide = guide if isinstance(guide, dict) else {}
    result = [f'<h3>Что модель может собрать: {len(capabilities)} capabilities</h3>',
              '<p>Это каталог разрешённых деталей, не список уже выбранных механик. '
              'Для этого формата каждый параметр обязателен, если нет optional: true. '
              'Neutral сам по себе не разрешает пропуск. Default не означает универсальное автозаполнение; '
              'условия пропуска и совместные зависимости сохраняются. В Repair пропуск может означать «не менять».</p>']
    for index, card in enumerate(capabilities):
        if not isinstance(card, dict) or not isinstance(card.get("fn"), str):
            continue
        cp = pointer(pointer(path, "capabilities"), index)
        result.append(f'<details class="reading-card"><summary>{html.escape(str(card.get("fn", index)))}</summary>'
                      f'<div class="node-body"><div class="value">{prose(card.get("does", "Назначение не описано в does"))}</div>')
        if "targets" in card:
            result.append('<div>Применяется к: ' + prose(card["targets"]) + '</div>')
        elif isinstance(card.get("targetsRef"), str):
            ref = card["targetsRef"]
            sets = guide.get("targetKindSets", {})
            targets = sets.get(ref) if isinstance(sets, dict) else None
            result.append('<div>Применяется к: ' + prose(targets if targets is not None else ref) + ' · ' +
                          source_link(pointer(pointer(pointer(path, "fieldGuide"), "targetKindSets"), ref), "targetsRef") + '</div>')
        for key in ("acceptedEvents", "requires", "constructionMeaning", "exclusiveGroup"):
            if key in card:
                result.append(f'<div class="value"><b>{html.escape(key)}</b>: {prose(card[key])}</div>')
        result.append('<dl>')
        params = card.get("params", {})
        for name, original in params.items() if isinstance(params, dict) else []:
            pp = pointer(pointer(cp, "params"), name)
            param = original
            reference = ""
            if isinstance(original, dict) and isinstance(original.get("paramRef"), str):
                fn, sep, target_name = original["paramRef"].partition(".")
                target, target_path = by_fn.get(fn, ({}, ""))
                target_params = target.get("params", {})
                borrowed = target_params.get(target_name) if isinstance(target_params, dict) else None
                if sep and isinstance(borrowed, dict) and "paramRef" not in borrowed:
                    param = borrowed
                    reference = ' Полная карточка взята из ' + source_link(pointer(pointer(target_path, "params"), target_name), original["paramRef"]) + '.'
                else:
                    param = None
                    reference = ' Неразрешённая ссылка: ' + prose(original["paramRef"]) + '. Требования не выведены.'
            result.append('<dt>' + source_link(pp, str(name)) + '</dt><dd>')
            if isinstance(param, dict):
                result.append('<div class="value">' + html.escape(param_sentence(param)) + '</div>')
                meaning, meaning_path, meaning_source = param_documentation(card["fn"], name, param, guide, by_fn, path)
                if meaning is not None:
                    result.append('<div class="value">' + prose(meaning) + '</div>')
                    if meaning_path:
                        result.append(source_link(meaning_path, 'Источник пояснения: ' + meaning_source))
                else:
                    result.append('<small>Отдельное пояснение смысла отсутствует в этом пакете; значение не угадывается.</small>')
                for key, group in (("typeRef", "types"), ("consumerConstraint", "consumerConstraints"),
                                   ("projectionConstraints", "consumerConstraints")):
                    if isinstance(param.get(key), str):
                        result.append(source_link(pointer(pointer(pointer(path, "fieldGuide"), group), param[key]), key + ": " + param[key]) + ' ')
                rendered_keys = {"optional", "type", "typeRef", "enum", "const", "minimum", "maximum", "min", "max",
                                 "exclusiveMinimum", "exclusiveMaximum", "units", "default", "neutral",
                                 "omissionAllowedOnlyWhen", "meaning", "pattern", "multipleOf"}
                for key, extra in param.items():
                    if key in rendered_keys or (key in {"consumerConstraint", "projectionConstraints"} and isinstance(extra, str)):
                        continue
                    result.append('<details><summary>' + html.escape(LABELS.get(key, key)) +
                                  '</summary><div class="value">' + prose(extra) + '</div></details>')
            else:
                result.append('<div class="value">' + prose(original) + '</div>')
            result.append(reference + '</dd>')
        result.append('</dl>')
        for key, extra in card.items():
            if key not in {"fn", "does", "targets", "targetsRef", "params", "acceptedEvents", "requires", "constructionMeaning", "exclusiveGroup"}:
                result.append('<details><summary>' + html.escape(key) + '</summary><div class="value">' + prose(extra) + '</div></details>')
        result.append(source_link(cp, 'Вся карточка: все условия и исходные поля') + '</div></details>')
    return "".join(result)


def reading_layer(value):
    # The capture's evidence is provenance, not model input. It remains fully
    # available in the lossless view, but never presented as a model instruction.
    request = value.get("request", value) if isinstance(value, dict) else value
    base = "/request" if isinstance(value, dict) and "request" in value else ""
    result = ['<section id="reading"><h2>Прочитать крафт</h2><p>Ниже — детерминированная раскладка известных разделов: '
              'какие исходные вещи переданы, чего требует ответ и какие детали доступны модели. '
              'Английские формулировки оставлены дословно: пересказ не должен скрыть спорную инструкцию. '
              'Полное дерево ниже содержит также неизвестные поля и все ограничения.</p>']
    found = list(documents(request, base))
    # Show the actual ingredients before reading long instruction/catalog blocks.
    found.sort(key=lambda row: 0 if isinstance(row[1], dict) and "parents" in row[1] else 1)
    for path, node in found:
        if not isinstance(node, dict):
            continue
        if isinstance(node.get("parents"), dict):
            result.append('<h3>Из чего собираем</h3>')
            for name, parent in node["parents"].items():
                pp = pointer(pointer(path, "parents"), name)
                packet = parent.get("packet", parent) if isinstance(parent, dict) else {}
                identity = packet.get("name", "Имя не указано") if isinstance(packet, dict) else "Неизвестная форма"
                result.append(f'<p><b>{html.escape(str(name))}: {html.escape(str(identity))}</b> · ' + source_link(pp, 'Все факты и механики этого родителя') + '</p>')
        if "priorityHeader" in node:
            result.append('<h3>Как модели велено принимать решения</h3><div class="value">' + prose(node["priorityHeader"]) + '</div>' + source_link(pointer(path, "priorityHeader")))
        shape = node.get("requiredJsonShape")
        if isinstance(shape, dict):
            result.append('<h3>Что требуется вернуть</h3>')
            if "root" in shape:
                result.append('<div>Обязательные корневые поля: ' + prose(shape["root"]) + '</div>')
            if "optionalAdvisory" in shape:
                result.append('<div>Необязательные пояснения: ' + prose(shape["optionalAdvisory"]) + '</div>')
            result.append(source_link(pointer(path, "requiredJsonShape"), 'Полная форма ответа и требования к каждому полю'))
        if isinstance(node.get("capabilities"), list) and isinstance(node.get("fieldGuide"), dict) and "authoringSchema" in node:
            result.append(capability_cards(node, path))
    result.append('</section>')
    return "".join(result)


def build_report(raw: bytes, source_name: str):
    value = strict_json(raw.decode("utf-8-sig"))
    if not isinstance(value, (dict, list)):
        raise ValueError("Expected a JSON object or array (saved request or dossier)")
    sha = hashlib.sha256(raw).hexdigest()
    markdown = [f"Аудит запроса: {source_name}", f"SHA-256 исходника: {sha}",
                "Полная читаемая проекция. Ничего не удалено и не переведено моделью.",
                "Пути — JSON Pointer; :: — вход в JSON, сохранённый внутри строки.",
                "Размеры узлов — compact JSON в символах, перекрываются; не токены.", ""]
    leaves = []
    refs = {}
    for definition_path, definition in documents(value):
        if isinstance(definition, dict) and isinstance(definition.get("$defs"), dict):
            for name in definition["$defs"]:
                ref = pointer("#/$defs", name)
                refs.setdefault(ref, []).append(pointer(pointer(definition_path, "$defs"), name))
    sections, nav, sizes = [], [], []
    for key, child in iter_children(value):
        path = pointer("", key)
        sections.append(render_node(str(key), child, path, 0, markdown, leaves, refs))
        nav.append(f'<a href="#{anchor(path)}">{html.escape(label(key, child))}</a>')
        sizes.append((label(key, child), serialized_chars(child)))
    # Message content is a more useful non-overlapping reading budget than an
    # enclosing wrapper. All other input fields still appear below, unchanged.
    request = value.get("request", value) if isinstance(value, dict) else value
    message_sizes = []
    if isinstance(request, dict):
        rows = request.get("messages", request.get("input"))
        if isinstance(rows, list):
            for index, row in enumerate(rows):
                if isinstance(row, dict):
                    content = row.get("content", "")
                    count = len(content) if isinstance(content, str) else serialized_chars(content)
                    message_sizes.append((f"{index}: {row.get('role', '(без role)')}", count))
    for path, node in documents(request, "/request" if request is not value else ""):
        if isinstance(node, dict):
            for key in node:
                if key in {"priorityHeader", "runtimeProgramInvariants", "runtimeCapabilityContract", "requiredJsonShape", "schemaDefinitions", "parents", "balanceCorridor", "fieldGuide"}:
                    nav.append(f'<a href="#{anchor(pointer(path, key))}">{html.escape(LABELS.get(key, key))}</a>')
    budget = message_sizes or sizes
    total = sum(size for _, size in budget)
    size_html = "".join(f'<li>{html.escape(title)}: <b>{size:,}</b> ({size / total:.1%})</li>' if total else
                        f'<li>{html.escape(title)}: 0</li>' for title, size in budget)
    metadata = {"source": source_name, "sourceSha256": sha, "sourceBytes": len(raw),
                "sourceCharacters": len(raw.decode("utf-8-sig")), "visibleLeafCount": len(leaves),
                "sizeBasis": "literal message content, or compact JSON top-level values; not token counts"}
    evidence = value.get("evidence") if isinstance(value, dict) else None
    if isinstance(evidence, dict) and isinstance(evidence.get("revision"), str):
        metadata["sourceRevisionDeclaredInEvidence"] = evidence["revision"]
    template = Path(__file__).with_name("prompt_audit_template.html").read_text(encoding="utf-8")
    substitutions = {
        "TITLE": html.escape(source_name), "REVISION": html.escape(metadata.get("sourceRevisionDeclaredInEvidence", "не указана в исходнике")), "METADATA": html.escape(json.dumps(metadata, ensure_ascii=False, indent=2)),
        "NAV": "".join(nav), "READING": reading_layer(value), "CONTENT": "".join(sections), "SIZES": size_html,
        "RAW": base64.b64encode(raw).decode("ascii"),
        "MARKDOWN": base64.b64encode(("\n".join(markdown) + "\n").encode("utf-8")).decode("ascii"),
    }
    # Single pass: input text containing template tokens must remain literal.
    import re
    rendered = re.sub(r"@@(TITLE|REVISION|METADATA|NAV|READING|CONTENT|SIZES|RAW|MARKDOWN)@@", lambda m: substitutions[m[1]], template)
    return rendered, "\n".join(markdown) + "\n", metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="stage_requests JSON, .builder.json, HTTP body, or a plain dossier")
    parser.add_argument("--out", type=Path, help="New HTML path (default: input.audit.html); existing files are refused")
    parser.add_argument("--markdown", type=Path, help="Also save a readable text/Markdown file")
    args = parser.parse_args(argv)
    out = args.out or args.input.with_suffix(".audit.html")
    paths = [out] + ([args.markdown] if args.markdown else [])
    try:
        if len({p.resolve() for p in paths}) != len(paths):
            raise ValueError("Output paths must be distinct")
        if any(p.exists() or p.is_symlink() for p in paths):
            raise ValueError("Output already exists; choose new paths (input is never overwritten)")
        document, markdown, metadata = build_report(args.input.read_bytes(), args.input.name)
        # Exclusive writes protect existing files, including the input, from races.
        for path, content in zip(paths, [document, markdown]):
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
    except (OSError, ValueError, RecursionError) as exc:
        print(f"prompt-audit: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"html": str(out), "markdown": str(args.markdown) if args.markdown else None, **metadata}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
