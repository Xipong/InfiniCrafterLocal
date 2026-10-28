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
from html.parser import HTMLParser
import re
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


# Reader annotations, not model instructions. Exact source hashes prevent an old
# explanation from silently attaching to a changed rule. Unknown rules keep only
# their complete original. This deliberately covers six observed Author rules,
# rather than building a second, translated capability registry.
INSTRUCTION_NOTES = {
    "68965badad7117a9134f770921ab8e6b0ec2d0c645d9b58e1a9165fb8f03a53f": (
        "Игровая цель и свобода дизайна",
        "Придумать полезное сочетание двух родителей. Механики, управление, сила и затраты должны работать вместе. "
        "Простые комбинации, узкая польза, сайдгрейды и бесплатные длительные эффекты допустимы; обязательного твиста нет."),
    "52e0f0e61654b60c975c42d4024fb12ae9b4db55042dd6d7eb3e1eef7581cdc3": (
        "Метаданные не создают механику",
        "Категория, название, теги и описание сами по себе ничего не исполняют. "
        "Всё поведение предмета модель должна явно записать в runtimeProgram."),
    "ffca7c3490437a4c8b2ca94f68a7300a3dddac8cd539873ce08de0e82e2208a9": (
        "Граница возможностей движка",
        "Разрешены только возможности, перечисленные в переданном каталоге capabilities."),
    "bff8357e5fdeac71c5ff172f0bf25be782d3181deafe90e99ed76be0d6ce1969": (
        "Из чего складываются эффекты",
        "Баффы и дебаффы собираются из явных примитивов: получатель, изменения, активация, длительность и шанс. "
        "Название знакомого баффа не переносит его скрытое поведение. Неизвестные свойства родителей нельзя выдавать за установленные."),
    "cfc2a55b82d97c64a97fb8ccc593002ddeeb892d76b38b01a1f455f0954768a1": (
        "Положение, управление и столкновения независимы",
        "Привязка к руке, направление, поза, движение, срок жизни и столкновения выбираются отдельно. "
        "Размер картинки и роль сущности не дописывают эти механики автоматически; отдельные выстрелы и превращения разрешены."),
    "65703a373ce575ab54dcfc608f175f4fd84cce318f120525b422a443df26ebde": (
        "Идентификаторы без пересечений",
        "Все ID должны быть стабильными, в нижнем snake_case и уникальными среди сущностей, связей и вызовов."),
}


class ReadingText(HTMLParser):
    """Copy all reading content, retaining literal data and source pointers.

    Only inserted layout separators are coalesced; whitespace inside source
    strings is data and must never be normalized. Closed details are included.
    """
    blocks = {"p", "div", "article", "section", "h2", "h3", "h4", "li", "dt", "dd", "summary", "details", "br"}

    def __init__(self):
        super().__init__()
        self.parts = []
        self.ignored = 0
        self.link_sources = []

    def boundary(self):
        if self.parts and self.parts[-1][0] != "layout":
            self.parts.append(("layout", "\n\n"))

    def handle_starttag(self, tag, attrs):
        if tag == "button":
            self.ignored += 1
        if not self.ignored:
            if tag in self.blocks:
                self.boundary()
            if tag == "a":
                self.link_sources.append(dict(attrs).get("data-source", ""))

    def handle_endtag(self, tag):
        if tag == "button":
            self.ignored -= 1
        if not self.ignored:
            if tag == "a" and self.link_sources:
                source = self.link_sources.pop()
                if source:
                    self.parts.append(("data", " [" + source + "]"))
            if tag in self.blocks:
                self.boundary()

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(("data", data))


def reading_text(markup):
    reader = ReadingText()
    reader.feed(markup)
    if reader.parts and reader.parts[-1][0] == "layout":
        reader.parts.pop()
    return "".join(text for _, text in reader.parts) + "\n"


def copy_button(markup, caption="Копировать раздел", *, plain=None):
    encoded = base64.b64encode((reading_text(markup) if plain is None else plain).encode("utf-8")).decode("ascii")
    return f'<button type="button" class="copy-button" data-copy="{encoded}">{html.escape(caption)}</button>'


def instruction_cards(value, path):
    if not isinstance(value, list):
        return prose(value)
    rows = []
    for index, rule in enumerate(value):
        number = f"{index + 1}. "
        rule_path = pointer(path, index)
        note = INSTRUCTION_NOTES.get(hashlib.sha256(rule.encode()).hexdigest()) if isinstance(rule, str) else None
        title, explanation = note if note else ("Инструкция из запроса", None)
        body = '<h4><span class="literal-number">' + number + '</span>' + html.escape(title) + '</h4>'
        if explanation:
            body += '<p class="reader-note"><b>Пояснение для аудита, не полный перевод:</b> ' + html.escape(explanation) + '</p>'
        else:
            body += '<p class="reader-note">Готового пояснения этой версии нет. Ниже полный исходный текст.</p>'
        # Split only whitespace after a sentence boundary. Original source bytes
        # remain downloadable; the source-copy control retains the exact string.
        chunks = re.split(r"(?<=[.!?])\s+(?=[A-ZА-Я])", rule) if isinstance(rule, str) else [rule]
        body += '<div class="original-rule" data-reader-path="' + html.escape(rule_path, quote=True) + '"><b>Оригинал, без сокращений</b>'
        body += ''.join('<p>' + prose(chunk) + '</p>' for chunk in chunks) + '</div>'
        body += source_link(rule_path, "Исходный пункт " + str(index + 1))
        source_markup = '<span>' + number + '</span>' + prose(rule)
        rows.append('<article class="instruction-card">' + body + copy_button(body, "Копировать пункт с пояснением") +
                    copy_button(source_markup, "Копировать оригинал пункта", plain=number + rule if isinstance(rule, str) else None) + '</article>')
    return ''.join(rows)


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
    return f'<a data-source="{html.escape(path, quote=True)}" href="#{anchor(path)}">{html.escape(caption)}</a>'


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
        return '<ol class="literal-list">' + ''.join('<li><span class="literal-number">' + str(index + 1) + '. </span>' + prose(child) + '</li>' for index, child in enumerate(value)) + '</ol>'
    return '<span class="empty">Пустая строка ("")</span>' if value == "" else html.escape(scalar(value))


def compact_words(value):
    if isinstance(value, list):
        return ', '.join(compact_words(child) for child in value) or 'пустой список'
    if isinstance(value, dict):
        return '; '.join(f'{key}: {compact_words(child)}' for key, child in value.items()) or 'пустой объект'
    return 'пустая строка ("")' if value == "" else scalar(value)


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
        card_start = len(result)
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
        result.append(source_link(cp, 'Вся карточка: все условия и исходные поля'))
        result.append(copy_button(''.join(result[card_start:]), 'Копировать всю карточку'))
        result.append('</div></details>')
    return "".join(result)


# Presentation glossary: labels explain structure; source prose stays authoritative.
LABELS.update({
    "catalog": "Каталог разрешённых игровых деталей", "technicalNotes": "Как читать числа и исходные факты",
    "entityKinds": "Какие сущности можно создать", "inputs": "Доступные способы активации",
    "bindingActions": "Действия привязок", "events": "События исполнения", "limits": "Жёсткие лимиты композиции",
    "packet": "Полный пакет предмета", "raw": "Исходные игровые сведения", "name": "Название",
    "internalName": "Внутреннее имя", "sourceMod": "Мод-источник", "recipeKey": "Идентификатор рецепта",
    "fn": "Имя исполняемой функции", "targets": "К каким сущностям применяется", "targetsRef": "Ссылка на набор допустимых целей",
    "paramRef": "Полная карточка параметра по ссылке", "typeRef": "Тип по общему определению",
    "acceptedEvents": "При каких событиях допустим вызов", "exclusiveGroup": "Группа несовместимости",
    "constructionMeaning": "Смысл при построении предмета", "apiVersion": "Версия игрового API",
    "authoringSchema": "Версия авторского формата", "schema": "Формат данных", "role": "Роль",
    "content": "Полное содержимое сообщения", "model": "Модель в сохранённом запросе",
    "temperature": "Параметр вариативности", "max_tokens": "Лимит токенов ответа",
    "runtimeProgram": "Исполняемая программа предмета", "concept": "Замысел (пояснение, не исполнение)",
    "realization": "Пояснение реализованных механик", "root": "Обязательные корневые поля ответа",
    "optionalAdvisory": "Необязательные пояснения", "entities": "Сущности", "bindings": "Привязки управления",
    "calls": "Вызовы игровых функций", "primaryEntityId": "Главная сущность предмета",
    "parentDamage": "Наблюдаемый урон родителей", "parentUseTimeTicks": "Время использования родителей в тиках",
    "parentProgressionFacts": "Известные факты о стадии игры", "broadEnvelope": "Широкие числовые ориентиры",
    "authority": "Статус и полномочия этих данных", "rule": "Правило применения", "readingRule": "Как читать раздел",
    "fieldColumns": "Смысл колонок", "scopes": "Области действия единиц", "time": "Время", "distance": "Расстояние",
    "speed": "Скорость и ускорение", "scope": "Границы применения", "spread": "Разброс",
    "id": "Идентификатор", "targetId": "Целевая сущность", "itemEntityId": "Сущность предмета в инвентаре",
    "generatedParent": "Сохранённый сгенерированный родитель", "gameplay": "Числовые игровые характеристики",
    "summary": "Сохранённое описание предмета", "identity": "Точная идентичность", "playerExperience": "Практическое использование",
    "damage": "Урон", "damageClass": "Класс урона", "knockback": "Отбрасывание", "enabled": "Включено",
    "spawn": "Порождение сущности", "aim": "Прицеливание", "placement": "Размещение", "count": "Количество",
    "hitbox": "Область столкновений", "collision": "Правила столкновений", "attachment": "Привязка положения",
    "targeting": "Поиск цели и стрельба", "shotEntityId": "Сущность выпускаемого выстрела",
    "searchRangeTiles": "Дальность поиска в блоках", "requireLineOfSight": "Требовать прямую видимость",
    "intervalTicks": "Интервал в тиках", "lifetimeTicks": "Время жизни в тиках", "rangeTiles": "Дальность в блоках",
    "speedPxPerTick": "Исходная скорость (единицы см. sourceWireUnits)", "widthPx": "Ширина в пикселях", "heightPx": "Высота в пикселях",
    "visualRole": "Роль изображения", "usePolicy": "Правила использования", "action": "Действие",
    "stackCost": "Расход предметов из стопки", "contactDamage": "Контактный урон", "itemUse": "Использование предмета",
    "rotation": "Вращение", "ownerControl": "Управление владельцем", "light": "Свет", "seek": "Наведение",
    "accessory": "Эффекты аксессуара", "armor": "Эффекты брони", "manaCost": "Затраты маны",
    "types": "Общие типы параметров", "consumerConstraints": "Ограничения исполняющего кода",
    "sourceInterpretation": "Как трактовать данные родителей", "targetKindSets": "Общие наборы типов целей",
    "primaryEntityOwnership": "Выбор главной сущности", "exactlyOnePrimaryEntity": "Главная сущность должна быть ровно одна",
    "authoredField": "Поле, которое заполняет модель", "primaryRule": "Правило выбора главной сущности",
    "graphAndSpawnBudget": "Связи событий и бюджет порождения", "json_schema": "Схема JSON-ответа",
    "strict": "Строгий режим схемы", "minLength": "Минимальная длина", "maxLength": "Максимальная длина",
    "minItems": "Минимум элементов", "maxItems": "Максимум элементов", "title": "Заголовок определения",
})
SECTION_HELP = {
    "parents": "Это фактические входные предметы, а не результат генерации. Ниже сохранены все сведения, включая их готовые программы и исходные числа.",
    "balanceCorridor": "Отделяйте наблюдаемые числа родителей от широких ориентиров. Они сами по себе не доказывают стадию игры или ожидаемую силу. Ноль в сводном parentDamage не доказывает отсутствие урона у отдельных сущностей родителя. Null означает отсутствие значения, а не ноль; пустой список фактов о прогрессии не означает раннюю стадию игры.",
    "runtimeCapabilityContract": "Это словарь разрешённых строительных деталей. Наличие функции здесь не означает, что она уже выбрана для нового предмета.",
    "fieldGuide": "Общие правила распространяются на карточки каталога. Читайте их вместе с локальными единицами, ссылками и ограничениями параметров.",
    "requiredJsonShape": "Это требования к будущему ответу, не готовый предмет. Примеры строк и идентификаторов не следует принимать за автоматически выбранные значения.",
    "response_format": "Машинный контракт ответа провайдеру. Поля и вложенные определения ниже раскрыты для проверки человеком, без удаления ограничений.",
    "params": "Параметры capability обязательны, если явно не указан optional: true. Neutral не разрешает пропуск сам по себе; default не означает универсальное автозаполнение.",
    "sourceWireUnits": "Единицы исходных фактов могут отличаться от единиц авторской программы. Применяйте только указанное здесь соответствие, а не догадку по названию.",
    "runtimeProgramInvariants": "Условия, которым должна удовлетворять вся композиция, независимо от отдельных выбранных функций.",
    "properties": "Определения полей объекта. Обязательность задаётся отдельным списком required именно этого объекта; наличие поля в properties само по себе не делает его обязательным.",
    "evidence": "Контекст захвата и происхождения. Это не следует считать инструкцией, отправленной модели.",
}


def reading_id(path):
    return "read-" + anchor(path)


INPUT_NAMES = {'primary_use': 'основное использование', 'alternate_use': 'альтернативное использование',
               'hold': 'удержание предмета', 'held': 'удержание предмета', 'equipped': 'ношение предмета'}
ACTION_NAMES = {'spawn_entity': 'создать сущность', 'apply_item_effects': 'применить эффекты предмета',
                'place_item': 'разместить предмет', 'use_item_body': 'использовать тело предмета', 'equip_passive': 'применить пассивное оснащение'}
ENTITY_NAMES = {'item_body': 'тело предмета', 'owner_attached_projectile': 'снаряд, привязанный к владельцу',
                'stationary_projectile': 'неподвижный снаряд', 'child_projectile': 'дочерний снаряд',
                'free_projectile': 'свободный снаряд', 'placed_tile': 'размещённый блок'}


def token_name(value, names):
    text = str(value)
    return names[text] + ' (' + text + ')' if text in names else text


def parent_relationships(program):
    """Describe explicit saved-wire relationships, without inventing behavior."""
    rows = []
    if isinstance(program.get('primaryEntityId'), str):
        rows.append('Главная сущность уже существующего родителя: ' + program['primaryEntityId'] + '.')
    for entity in program.get('entities', []) if isinstance(program.get('entities'), list) else []:
        if not isinstance(entity, dict):
            continue
        name = str(entity.get('id', '(без id)'))
        rows.append('Сущность ' + name + ' имеет тип ' + token_name(entity.get('kind', '(не указан)'), ENTITY_NAMES) + '.')
        targeting = entity.get('targeting')
        if isinstance(targeting, dict) and isinstance(targeting.get('shotEntityId'), str):
            rows.append(name + ' ссылается на ' + targeting['shotEntityId'] + ' как на выпускаемый выстрел; полный набор условий стрельбы сохранён в разделе «Поиск цели и стрельба».')
    for binding in program.get('bindings', []) if isinstance(program.get('bindings'), list) else []:
        if not isinstance(binding, dict):
            continue
        policy = binding.get('usePolicy', binding)
        action = policy.get('action') if isinstance(policy, dict) else None
        if isinstance(action, dict):
            rows.append('Привязка ' + str(binding.get('id', '(без id)')) + ': вход ' + token_name(binding.get('input', '(не указан)'), INPUT_NAMES) + ' → действие ' + token_name(action.get('kind', '(не указано)'), ACTION_NAMES) + ' → сущность ' + str(action.get('targetId', '(не указана)')) + '. Условия и затраты смотрите в полной карточке этой привязки.')
    if not rows:
        return ''
    return '<div class="reader-note"><b>Связи в сохранённой механике родителя</b><p>Это чтение явных ID и ссылок, не оценка силы и не предложение механики нового предмета.</p>' + ''.join('<p>' + html.escape(row) + '</p>' for row in rows) + '</div>'


def parent_field_notes(request, base):
    """Join only exact source scopes to explicit Author cards; never infer units."""
    found = list(documents(request, base))
    catalogs = [(path, node) for path, node in found if isinstance(node, dict) and 'authoringSchema' in node and isinstance(node.get('capabilities'), list)]
    notes = {}
    if len(catalogs) != 1:
        return notes
    catalog_path, catalog = catalogs[0]
    named = [(card, i) for i, card in enumerate(catalog['capabilities']) if isinstance(card, dict) and isinstance(card.get('fn'), str)]
    by_fn = {card['fn']: (card, pointer(pointer(catalog_path, 'capabilities'), i)) for card, i in named if sum(other['fn'] == card['fn'] for other, _ in named) == 1}

    def resolve(node, path, dotted):
        rows = [(node, path)]
        for part in dotted.split('.'):
            array = part.endswith('[]')
            name = part[:-2] if array else part
            next_rows = []
            for current, current_path in rows:
                if not isinstance(current, dict) or name not in current:
                    continue
                child, child_path = current[name], pointer(current_path, name)
                if array and isinstance(child, list):
                    next_rows.extend((item, pointer(child_path, i)) for i, item in enumerate(child))
                elif not array:
                    next_rows.append((child, child_path))
            rows = next_rows
        return rows

    for path, node in found:
        if not isinstance(node, dict) or not isinstance(node.get('parents'), dict) or not isinstance(node.get('sourceWireUnits'), dict):
            continue
        scopes = node['sourceWireUnits'].get('scopes', [])
        for parent_key, parent in node['parents'].items():
            if not isinstance(parent, dict) or not isinstance(parent.get('packet'), dict):
                continue
            packet_path = pointer(pointer(pointer(path, 'parents'), parent_key), 'packet')
            for i, scope in enumerate(scopes if isinstance(scopes, list) else []):
                if not isinstance(scope, dict) or not isinstance(scope.get('source'), str) or not isinstance(scope.get('fields'), dict) or not isinstance(scope.get('fn'), str):
                    continue
                for container, container_path in resolve(parent['packet'], packet_path, scope['source']):
                    when = scope.get('when', {})
                    if not isinstance(when, dict) or any(not any(actual == expected for actual, _ in resolve(container, container_path, key)) for key, expected in when.items()):
                        continue
                    for field, row in scope['fields'].items():
                        if not isinstance(row, list) or len(row) != 3:
                            continue
                        for _, field_path in resolve(container, container_path, field):
                            rule_path = pointer(pointer(pointer(pointer(path, 'sourceWireUnits'), 'scopes'), i), 'fields')
                            note = 'Явное соответствие единиц: ' + str(scope.get('fn')) + '.' + str(row[0]) + '; формула: ' + str(row[1]) + '; единицы Author: ' + str(row[2] or '(не объявлены)') + '. '
                            markup = html.escape(note) + source_link(pointer(rule_path, field), 'Правило исходника')
                            card, card_path = by_fn.get(scope.get('fn'), ({}, ''))
                            name = str(row[0]).split('.')[0]
                            param = card.get('params', {}).get(name) if isinstance(card.get('params'), dict) else None
                            if isinstance(param, dict):
                                markup += ' · <a href="#' + reading_id(pointer(pointer(card_path, 'params'), name)) + '">Смысл и ограничения параметра</a>'
                            notes.setdefault(field_path, []).append(markup)
    return notes


def readable_value(key, value, path, depth=0, catalog=None, catalog_path="", fn=None, field_notes=None):
    """Complete semantic projection, not a raw JSON tree or selected-field summary.

    Every literal/empty container has an auditable path. Containers become titled
    groups, prose paragraphs, numbered lists and field definitions. No JSON syntax
    is exposed and no source fact is filtered by a whitelist.
    """
    decoded = decode_content(str(key), value)
    if decoded is not None:
        return readable_value(key, decoded, path + "::", depth, catalog, catalog_path, fn, field_notes)
    title = LABELS.get(str(key), str(key))
    if '/meaningByToken/' in path:
        title = 'Значение токена · ' + str(key)
    if str(key) == 'input':
        title = 'Способ активации' if re.search(r'/bindings/[0-9]+/input$', path) else 'Входные данные'
    is_catalog = isinstance(value, dict) and isinstance(value.get("capabilities"), list) and "authoringSchema" in value
    if is_catalog:
        catalog, catalog_path = value, path
    is_capability = isinstance(value, dict) and isinstance(value.get("fn"), str)
    if is_capability:
        fn = value["fn"]
        title = "Игровая функция · " + fn
    elif isinstance(value, dict) and isinstance(value.get('id'), str):
        title = 'Запись · ' + value['id']
    elif isinstance(value, dict) and isinstance(value.get("role"), str) and 'content' in value:
        title = {"system": "Системное сообщение", "developer": "Инструкции разработчика", "user": "Данные крафта"}.get(value["role"], "Сообщение · " + value["role"])
    elif isinstance(value, dict) and isinstance(value.get("packet"), dict):
        title = "Предмет " + str(key) + " · " + str(value["packet"].get("name", "без названия"))
    if isinstance(key, int):
        title = str(key + 1) + ". " + (title if title != str(key) else "Элемент")
    heading = html.escape(title)
    if title != str(key) and not isinstance(key, int):
        heading += ' <small class="wire-key">' + html.escape(str(key)) + '</small>'
    source = source_link(path, "Источник")
    if not isinstance(value, (dict, list)) or not value:
        data = prose(value)
        if field_notes and path in field_notes:
            data += '<div class="field-explanation">' + '<br>'.join(field_notes[path]) + '</div>'
        kind = scalar_type(value) if not isinstance(value, (dict, list)) else ("object" if isinstance(value, dict) else "array")
        return ('<div class="read-field" id="' + reading_id(path) + '" data-reader-path="' + html.escape(path, quote=True) + '">'
                '<div class="read-label">' + heading + ' <small>' + html.escape(kind) + '</small></div>'
                '<div class="read-value">' + data + '</div><div class="read-origin">' + source + '</div></div>')
    parts = []
    if isinstance(value, dict) and str(key) == 'runtimeProgram' and '/parents/' in path:
        parts.append(parent_relationships(value))
    if str(key) in SECTION_HELP and (str(key) != 'params' or (catalog is not None and '/capabilities/' in path)):
        parts.append('<p class="section-help">' + html.escape(SECTION_HELP[str(key)]) + '</p>')
    # Resolve only explicit documentation references. Original cards remain below.
    if isinstance(value, dict) and '/params/' in path and '/' not in path.rsplit('/params/', 1)[1] and catalog and fn:
        cards = catalog.get('capabilities', [])
        named = [(c, i) for i, c in enumerate(cards) if isinstance(c, dict) and isinstance(c.get('fn'), str)]
        by_fn = {c['fn']: (c, pointer(pointer(catalog_path, 'capabilities'), i)) for c, i in named if sum(other['fn'] == c['fn'] for other, _ in named) == 1}
        param = value
        if isinstance(value.get('paramRef'), str):
            target_fn, sep, target_param = value['paramRef'].partition('.')
            target, target_path = by_fn.get(target_fn, ({}, ''))
            borrowed = target.get('params', {}).get(target_param) if isinstance(target.get('params'), dict) else None
            if sep and isinstance(borrowed, dict) and 'paramRef' not in borrowed:
                parts.append('<div class="reader-note">Полная карточка по явной ссылке: ' + source_link(pointer(pointer(target_path, 'params'), target_param), value['paramRef']) + prose(borrowed) + '</div>')
                param = borrowed
            else:
                parts.append('<p class="reader-note">Ссылка не разрешена в этом пакете. Требования не угадываются.</p>')
        parts.append('<p class="parameter-contract">' + html.escape(param_sentence(param)) + '</p>')
        meaning, meaning_path, origin = param_documentation(fn, str(key), param, catalog.get('fieldGuide', {}) if isinstance(catalog.get('fieldGuide'), dict) else {}, by_fn, catalog_path)
        if meaning_path:
            parts.append('<div class="reader-note">Унаследованный смысл: ' + prose(meaning) + ' ' + source_link(meaning_path, origin) + '. Собственные единицы и границы остаются ниже.</div>')
    if str(key) == 'priorityHeader' and isinstance(value, list) and all(isinstance(rule, str) for rule in value):
        parts.append(instruction_cards(value, path))
    else:
        for child_key, child in iter_children(value):
            parts.append(readable_value(child_key, child, pointer(path, child_key), depth + 1, catalog, catalog_path, fn, field_notes))
    body = ''.join(parts)
    # Only meaningful chapter boundaries fold; fields remain directly readable.
    chapter = depth <= 1 or is_capability or str(key) in SECTION_HELP or str(key) in {'catalog', 'messages', 'requiredJsonShape', 'schemaDefinitions', '$defs'}
    if chapter:
        return ('<details open class="read-chapter" data-reader-container="' + html.escape(path, quote=True) + '" id="' + reading_id(path) + '"><summary>' + heading + '</summary>'
                '<div class="read-content">' + source + copy_button(body, "Копировать этот раздел") + body + '</div></details>')
    return '<div class="read-group" data-reader-container="' + html.escape(path, quote=True) + '" id="' + reading_id(path) + '"><h4>' + heading + '</h4>' + body + '</div>'


def reading_layer(value):
    request = value.get("request", value) if isinstance(value, dict) else value
    base = "/request" if isinstance(value, dict) and "request" in value else ""
    result = ['<section id="reading"><h2>Полный читаемый аудит</h2><p>Это весь сохранённый запрос, а не сокращённая выжимка. '
              'Сообщения идут в исходном порядке; каждая инструкция, факт, параметр и ограничение раскрыты ниже. '
              'Русские подписи объясняют структуру. Исходные формулировки сохранены на языке оригинала; пояснения не подменяют их.</p>']
    if not isinstance(request, (dict, list)) or not request:
        return ''.join(result) + readable_value('request', request, base) + '</section>'
    # Brief factual entry point; complete parent packets remain in their chapters.
    for parent_path, node in documents(request, base):
        if isinstance(node, dict) and isinstance(node.get('parents'), dict):
            result.append('<div class="parent-overview"><h3>Какие предметы переданы модели</h3>')
            for name, parent in node['parents'].items():
                packet = parent.get('packet', parent) if isinstance(parent, dict) else {}
                packet = packet if isinstance(packet, dict) else {}
                pp = pointer(pointer(parent_path, 'parents'), name)
                result.append('<article><h4>' + html.escape(str(name)) + ' · ' + html.escape(str(packet.get('name', 'Без названия'))) + '</h4>')
                generated = packet.get('raw', {}).get('generatedParent', {}) if isinstance(packet.get('raw'), dict) else {}
                summary = generated.get('summary', {}) if isinstance(generated, dict) else {}
                if isinstance(summary, dict) and isinstance(summary.get('description'), str):
                    result.append('<p class="read-value">' + html.escape(summary['description']) + '</p>')
                program = generated.get('runtimeProgram') if isinstance(generated, dict) else None
                if isinstance(program, dict):
                    primary = program.get('primaryEntityId')
                    if isinstance(primary, str):
                        result.append('<p><b>По сохранённой программе:</b> главная сущность — ' + html.escape(primary) + '. Это существующий родитель, не будущий результат крафта.</p>')
                    for binding in program.get('bindings', []) if isinstance(program.get('bindings'), list) else []:
                        if not isinstance(binding, dict):
                            continue
                        policy = binding.get('usePolicy', binding)
                        action = policy.get('action') if isinstance(policy, dict) else None
                        if isinstance(action, dict):
                            input_name = {'primary_use': 'Основное использование', 'alternate_use': 'Альтернативное использование', 'held': 'Удержание предмета', 'equipped': 'Ношение предмета'}.get(str(binding.get('input')), str(binding.get('input', 'Вход не указан')))
                            verb = {'spawn_entity': 'создаёт сущность', 'apply_item_effects': 'применяет эффекты к сущности'}.get(str(action.get('kind')), 'выполняет ' + str(action.get('kind')) + ' для')
                            result.append('<p>' + html.escape(input_name + ' ' + verb + ' ' + str(action.get('targetId', '(цель не указана)'))) + '. Полные условия и затраты — по ссылке ниже.</p>')
                result.append('<a href="#' + reading_id(pp) + '">Читать все факты, числа и механику этого предмета →</a></article>')
            result.append('</div>')
    chapters = []
    for key, child in iter_children(request):
        path = pointer(base, key)
        chapters.append((key, child, path))
    nav = '<div class="reading-toc"><b>Содержание полного аудита</b>'
    for key, child, path in chapters:
        nav += '<a href="#' + reading_id(path) + '">' + html.escape(LABELS.get(str(key), str(key))) + '</a>'
        if key in {'messages', 'input'} and isinstance(child, list):
            for i, msg in enumerate(child):
                if isinstance(msg, dict):
                    mp = pointer(path, i)
                    nav += '<a class="toc-child" href="#' + reading_id(mp) + '">' + str(i + 1) + '. ' + html.escape(str(msg.get('role', 'сообщение'))) + '</a>'
                    decoded = decode_content('content', msg.get('content'))
                    if isinstance(decoded, dict):
                        for k in decoded:
                            nav += '<a class="toc-child" href="#' + reading_id(pointer(pointer(mp, 'content') + '::', k)) + '">' + html.escape(LABELS.get(k, k)) + '</a>'
    result.append('<div class="reader-note"><b>Как читать термины</b><p>Сущность (entity) — отдельная часть программы с ID. Привязка (binding) связывает вход управления с действием. Capability — разрешённая исполняемая функция; call — конкретный её вызов. Каталог описывает, что можно выбрать, а программа родителя — что уже было выбрано.</p><p>Meaning / description — исходная документация смысла. Type — допустимый тип значения; units — единицы; min / max — границы. Default и neutral не взаимозаменяемы: наличие нейтрали не разрешает пропуск. Правила обязательности каталога отличаются от JSON Schema, где действует список required.</p><p>Русские подписи — помощь в чтении, а не новые правила. Где в пакете нет пояснения смысла, оно не выдумывается. Неизвестные поля остаются видимыми под исходным именем. Числа не пересчитываются без точного правила из sourceWireUnits.</p></div>')
    nav = re.sub(r'(<a\b[^>]*>.*?</a>)', r'<div>\1</div>', nav, flags=re.S)
    result.append(nav + '</div>')
    field_notes = parent_field_notes(request, base)
    result.extend(readable_value(key, child, path, field_notes=field_notes) for key, child, path in chapters)
    result.append('</section>')
    return ''.join(result)


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
        nav.append(f'<a href="#{reading_id(path)}">{html.escape(label(key, child))}</a>' if key != 'evidence' and not (key == 'request') else '')
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
                    nav.append(f'<a href="#{reading_id(pointer(path, key))}">{html.escape(LABELS.get(key, key))}</a>')
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
    reading = reading_layer(value)
    readable_prose = reading_text(reading)
    substitutions = {
        "TITLE": html.escape(source_name), "REVISION": html.escape(metadata.get("sourceRevisionDeclaredInEvidence", "не указана в исходнике")), "METADATA": html.escape(json.dumps(metadata, ensure_ascii=False, indent=2)),
        "NAV": "".join(nav), "READING": reading, "CONTENT": "".join(sections), "SIZES": size_html,
        "RAW": base64.b64encode(raw).decode("ascii"),
        "PROSE": base64.b64encode(readable_prose.encode("utf-8")).decode("ascii"),
        "MARKDOWN": base64.b64encode(("\n".join(markdown) + "\n").encode("utf-8")).decode("ascii"),
    }
    # Single pass: input text containing template tokens must remain literal.
    rendered = re.sub(r"@@(TITLE|REVISION|METADATA|NAV|READING|CONTENT|SIZES|RAW|MARKDOWN|PROSE)@@", lambda m: substitutions[m[1]], template)
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
