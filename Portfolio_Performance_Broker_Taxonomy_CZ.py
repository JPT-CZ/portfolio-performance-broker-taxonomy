#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V8: Přepočítá taxonomii „Podle brokera“; zapisuje XML minimálními bajtovými úpravami a zpracovává obě strany portfolio-transfer.

Používá pouze standardní knihovnu Pythonu. Portfolio Performance musí být zavřené.
Před změnou vypíše přehled a vyžádá si potvrzení ANO.
"""

from __future__ import annotations
import copy
import datetime as dt
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from xml.parsers import expat
from xml.sax.saxutils import escape, quoteattr
from collections import defaultdict

# ---------------------------------------------------------------------------
# NASTAVENÍ – uprav cestu k vlastnímu souboru Portfolio Performance.
# Příklad: r"C:\Users\Jana\Investice.portfolio"
# ---------------------------------------------------------------------------
PORTFOLIO_FILE = r"C:\CESTA\K\PORTFOLIU.portfolio"
TAXONOMY_NAME = "Podle brokera"
BACKUPS_TO_KEEP = 10
BACKUP_MARKER = ".Backup."
LOG_SUFFIX = "-Změna Vah"  # Text between the portfolio name and the timestamp in the log filename
PORTFOLIO_SUFFIX = " Portfolio"
# Nepovinné ruční mapování: přesný název účtu cenných papírů -> název třídy v taxonomii.
# Použij, pokud se název účtu neshoduje s názvem brokera ani po odebrání " Portfolio".
# Příklad: {"Moje krypto peněženka": "Coinbase"}
PORTFOLIO_TO_BROKER = {}
WEIGHT_TOTAL = 10000  # Portfolio Performance ukládá 100 % jako 10000
SHARES_SCALE = 100_000_000  # například 600000000 = 6 kusů; poměrům to nevadí


def fail(message: str) -> None:
    raise RuntimeError(message)


def local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def children_named(parent: ET.Element, name: str):
    return [child for child in list(parent) if local_tag(child.tag) == name]


def first_child(parent: ET.Element | None, name: str) -> ET.Element | None:
    if parent is None:
        return None
    for child in list(parent):
        if local_tag(child.tag) == name:
            return child
    return None


def find_child_text(parent: ET.Element | None, name: str) -> str | None:
    child = first_child(parent, name)
    return child.text.strip() if child is not None and child.text else None


def all_descendants_named(parent: ET.Element, name: str):
    return [el for el in parent.iter() if el is not parent and local_tag(el.tag) == name]


def find_section(root: ET.Element, name: str) -> ET.Element:
    section = first_child(root, name)
    if section is None:
        fail(f"V XML chybí sekce <{name}>.")
    return section


def is_zip_file(path: Path) -> bool:
    return zipfile.is_zipfile(path)


def load_source(path: Path):
    """Vrátí (xml_bytes, zip_entries_or_None, zip_comment, data_xml_name)."""
    if not path.is_file():
        fail(f"Soubor neexistuje: {path}")
    if is_zip_file(path):
        with zipfile.ZipFile(path, "r") as zf:
            names = [n for n in zf.namelist() if Path(n).name.lower() == "data.xml"]
            if len(names) != 1:
                fail("ZIP musí obsahovat právě jeden soubor pojmenovaný data.xml.")
            xml_name = names[0]
            entries = [(info, zf.read(info.filename)) for info in zf.infolist()]
            return zf.read(xml_name), entries, zf.comment, xml_name
    # Pro případ, že by uživatel nastavil přímo XML soubor.
    if path.suffix.lower() == ".xml":
        return path.read_bytes(), None, b"", None
    fail("Soubor není platný ZIP/Portfolio Performance archiv ani samostatné XML.")


def parse_security_reference(reference: str, securities: list[ET.Element]) -> int:
    """Vrátí index cenného papíru (1-based) z PP relativní XPath reference."""
    match = re.search(r"/securities/security(?:\[(\d+)\])?$", reference)
    if not match:
        fail(f"Neznámý odkaz na cenný papír v XML: {reference!r}")
    index = int(match.group(1) or "1")
    if index < 1 or index > len(securities):
        fail(f"Odkaz ukazuje na neexistující securities/security[{index}].")
    return index


def resolve_vehicle_index(assignment: ET.Element, securities: list[ET.Element]) -> int | None:
    vehicle = first_child(assignment, "investmentVehicle")
    if vehicle is None or vehicle.get("class") != "security":
        return None
    ref = vehicle.get("reference", "")
    return parse_security_reference(ref, securities)


def set_child_text(parent: ET.Element, name: str, value: str) -> None:
    child = first_child(parent, name)
    if child is None:
        child = ET.SubElement(parent, name)
    child.text = value


def format_share_value(value: float) -> str:
    """Zobrazí kusy až na 8 desetinných míst bez vědecké notace."""
    rendered = f"{value:.8f}".rstrip("0").rstrip(".")
    return rendered if rendered not in ("", "-0") else "0"


def round_weights(shares_by_broker: dict[str, int]) -> dict[str, int]:
    """Rozdělí 10000 jednotek přesně; zbytky přidělí metodou největších zbytků."""
    total = sum(shares_by_broker.values())
    if total <= 0:
        return {}
    raw = {name: amount * WEIGHT_TOTAL / total for name, amount in shares_by_broker.items()}
    result = {name: int(value) for name, value in raw.items()}
    remaining = WEIGHT_TOTAL - sum(result.values())
    order = sorted(raw, key=lambda name: (raw[name] - result[name], name), reverse=True)
    for name in order[:remaining]:
        result[name] += 1
    return result


def xml_bytes(root: ET.Element, original: bytes) -> bytes:
    # Zachovej deklaraci XML, pokud ji původní soubor měl.
    # ElementTree jinak zapíše znak CR (\r) přímo do XML. Při dalším načtení
    # XML parser převede takový CR na LF, což vyvolá falešný rozdíl v poznámkách.
    # Zápis CR jako znakové reference &#13; zachová původní obsah textu i po načtení.
    had_declaration = original.lstrip().startswith(b"<?xml")
    data = ET.tostring(root, encoding="utf-8", xml_declaration=had_declaration)
    return data.replace(b"\r", b"&#13;")


def write_temp(path: Path, xml_name: str | None, entries, zip_comment: bytes, xml_data: bytes) -> Path:
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".tmp-", dir=str(path.parent))
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        if entries is None:
            temp_path.write_bytes(xml_data)
        else:
            with zipfile.ZipFile(temp_path, "w") as out:
                out.comment = zip_comment
                for info, old_data in entries:
                    data = xml_data if info.filename == xml_name else old_data
                    # Zachová se původní ZipInfo včetně komprese, času a atributů.
                    out.writestr(info, data)
        return temp_path
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def backup_name(path: Path, now: dt.datetime) -> Path:
    stamp = now.strftime("%Y.%m.%d_%H-%M-%S")
    return path.with_name(f"{path.stem}{BACKUP_MARKER}{stamp}{path.suffix}")


def prune_backups(path: Path, keep: int) -> list[Path]:
    pattern = re.compile(r"^" + re.escape(path.stem + BACKUP_MARKER) + r"\d{4}\.\d{2}\.\d{2}_\d{2}-\d{2}-\d{2}" + re.escape(path.suffix) + r"$")
    backups = [p for p in path.parent.iterdir() if p.is_file() and pattern.match(p.name)]
    backups.sort(key=lambda p: p.name, reverse=True)
    deleted = []
    for old in backups[keep:]:
        old.unlink()
        deleted.append(old)
    return deleted


def clone_without_target_taxonomy(root: ET.Element, target_name: str) -> ET.Element:
    clone = copy.deepcopy(root)
    taxonomies = first_child(clone, "taxonomies")
    if taxonomies is not None:
        for tax in list(taxonomies):
            if local_tag(tax.tag) == "taxonomy" and find_child_text(tax, "name") == target_name:
                taxonomies.remove(tax)
    return clone


def canonical_without_target_taxonomy(root: ET.Element, target_name: str) -> bytes:
    clone = clone_without_target_taxonomy(root, target_name)
    return ET.tostring(clone, encoding="utf-8")


def describe_value(value: str | None, limit: int = 180) -> str:
    if value is None:
        return "None"
    value = repr(value)
    return value if len(value) <= limit else value[:limit - 3] + "..."


def find_xml_differences(old_root: ET.Element, new_root: ET.Element, target_name: str, limit: int = 12) -> list[str]:
    """Vypíše první konkrétní strukturální rozdíly mimo cílovou taxonomii."""
    old = clone_without_target_taxonomy(old_root, target_name)
    new = clone_without_target_taxonomy(new_root, target_name)
    differences: list[str] = []

    def walk(a: ET.Element, b: ET.Element, path: str) -> None:
        if len(differences) >= limit:
            return
        if a.tag != b.tag:
            differences.append(f"{path}: název uzlu {a.tag!r} -> {b.tag!r}")
            return
        if a.attrib != b.attrib:
            differences.append(f"{path}: atributy {a.attrib!r} -> {b.attrib!r}")
        if a.text != b.text:
            differences.append(f"{path}: text {describe_value(a.text)} -> {describe_value(b.text)}")
        if a.tail != b.tail:
            differences.append(f"{path}: koncový text/tail {describe_value(a.tail)} -> {describe_value(b.tail)}")
        ac, bc = list(a), list(b)
        if len(ac) != len(bc):
            differences.append(f"{path}: počet potomků {len(ac)} -> {len(bc)}")
        for i, (ca, cb) in enumerate(zip(ac, bc), 1):
            if len(differences) >= limit:
                break
            tag = local_tag(ca.tag)
            # Index uzlu stejného typu pro snazší orientaci v XML.
            same_type_index = sum(1 for prior in ac[:i] if local_tag(prior.tag) == tag)
            walk(ca, cb, f"{path}/{tag}[{same_type_index}]")

    walk(old, new, "/" + local_tag(old.tag))
    return differences



def _tag_end(data: bytes, start: int) -> int:
    """Najde index za > v XML tagu, respektuje uvozovky v atributech."""
    quote = None
    for i in range(start, len(data)):
        ch = data[i]
        if quote is not None:
            if ch == quote:
                quote = None
        elif ch in (34, 39):
            quote = ch
        elif ch == 62:  # >
            return i + 1
    raise RuntimeError("V XML se nepodařilo najít konec tagu.")


def index_xml_spans(data: bytes) -> dict[tuple[int, ...], tuple[int, int, int, int]]:
    """Mapuje cestu elementů (indexy potomků) na přesné bajtové rozsahy XML."""
    parser = expat.ParserCreate()
    spans = {}
    stack = []
    child_counts = []

    def start(name, attrs):
        start = parser.CurrentByteIndex
        start_end = _tag_end(data, start)
        if stack:
            idx = child_counts[-1]
            child_counts[-1] += 1
            path = stack[-1]["path"] + (idx,)
        else:
            path = ()
        stack.append({"path": path, "start": start, "start_end": start_end,
                      "self_closing": data[start:start_end].rstrip().endswith(b"/>")})
        child_counts.append(0)

    def end(name):
        item = stack.pop()
        child_counts.pop()
        if item["self_closing"]:
            end_start = item["start_end"]
            end_end = item["start_end"]
        else:
            end_start = parser.CurrentByteIndex
            end_end = _tag_end(data, end_start)
        spans[item["path"]] = (item["start"], item["start_end"], end_start, end_end)

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.Parse(data, True)
    return spans


def map_element_paths(root: ET.Element):
    paths = {}
    parents = {}
    elements = {}

    def walk(node, path=(), parent_id=None):
        ident = id(node)
        paths[ident] = path
        elements[ident] = node
        if parent_id is not None:
            parents[ident] = parent_id
        for index, child in enumerate(list(node)):
            walk(child, path + (index,), ident)

    walk(root)
    return paths, parents, elements


def _line_indent(data: bytes, position: int) -> tuple[int, bytes]:
    line_start = data.rfind(b"\n", 0, position) + 1
    prefix = data[line_start:position]
    if prefix.strip():
        return position, b""
    return line_start, prefix


def _assignment_xml(assignment: ET.Element, indent: bytes, child_indent: bytes) -> bytes:
    iv = first_child(assignment, "investmentVehicle")
    weight = find_child_text(assignment, "weight")
    rank = find_child_text(assignment, "rank")
    if iv is None or not iv.get("class") or not iv.get("reference") or weight is None or rank is None:
        raise RuntimeError("Nové přiřazení nemá očekávanou strukturu; XML nebylo změněno.")
    # Zachováme obvyklý zápis Portfolio Performance: bez mezery před /> a s odsazením.
    attrs = " ".join(f"{key}={quoteattr(value)}" for key, value in iv.attrib.items())
    lines = [
        indent + b"<assignment>\n",
        child_indent + f"<investmentVehicle {attrs}/ >".replace("/ >", "/>" ).encode("utf-8") + b"\n",
        child_indent + f"<weight>{escape(weight)}</weight>".encode("utf-8") + b"\n",
        child_indent + f"<rank>{escape(rank)}</rank>".encode("utf-8") + b"\n",
        indent + b"</assignment>\n",
    ]
    return b"".join(lines)


def apply_minimal_xml_patches(original_bytes: bytes, root: ET.Element,
                              original_state: dict, original_paths: dict,
                              original_parents: dict, original_elements: dict,
                              spans: dict, target_taxonomy: ET.Element) -> bytes:
    """Zapíše jen změněné hodnoty a assignmenty; zbytek XML ponechá bajt po bajtu."""
    current_paths, current_parents, current_elements = map_element_paths(root)
    current_ids = set(current_elements)
    original_ids = set(original_elements)
    taxonomy_path = original_paths[id(target_taxonomy)]

    def inside_target(path):
        return path[:len(taxonomy_path)] == taxonomy_path

    patches = []  # (start, end, replacement, description)

    # Původní elementy, které zmizely: dovolujeme pouze celé assignmenty v cílové taxonomii.
    missing_ids = original_ids - current_ids
    removed_roots = []
    for ident in missing_ids:
        parent_id = original_parents.get(ident)
        if parent_id not in missing_ids:
            removed_roots.append(ident)
    for ident in removed_roots:
        node = original_elements[ident]
        path = original_paths[ident]
        if local_tag(node.tag) != "assignment" or not inside_target(path):
            raise RuntimeError(f"Neočekávaně se odstranil element {local_tag(node.tag)} mimo podporovanou změnu; XML nebylo změněno.")
        start, start_end, end_start, end_end = spans[path]
        patch_start, _ = _line_indent(original_bytes, start)
        # Odstraň i whitespace/tail po assignmentu až k dalšímu tagu, aby
        # po odebrání nevznikaly prázdné řádky. Samotný další tag zůstane.
        next_tag = original_bytes.find(b"<", end_end)
        if next_tag >= 0:
            next_line_start, next_indent = _line_indent(original_bytes, next_tag)
            patch_end = next_line_start if not next_indent.strip() else end_end
        else:
            patch_end = end_end
        patches.append((patch_start, patch_end, b"", "odstranění zastaralého assignmentu"))

    # Existující elementy: povolujeme změnu textu pouze v hodnotě <weight>.
    for ident in original_ids & current_ids:
        old_node = original_elements[ident]
        new_node = current_elements[ident]
        old_tag, old_attrib, old_text, old_tail = original_state[ident]
        if dict(new_node.attrib) != old_attrib or new_node.tail != old_tail:
            raise RuntimeError(f"Neočekávaná změna atributů/odsazení u {local_tag(new_node.tag)}; XML nebylo změněno.")
        if new_node.text != old_text:
            path = original_paths[ident]
            if local_tag(new_node.tag) != "weight" or not inside_target(path):
                raise RuntimeError(f"Neočekávaná změna textu u {local_tag(new_node.tag)}; XML nebylo změněno.")
            if new_node.text is None or not re.fullmatch(r"-?\d+", new_node.text):
                raise RuntimeError("Nová hodnota váhy není celé číslo; XML nebylo změněno.")
            start, start_end, end_start, end_end = spans[path]
            patches.append((start_end, end_start, new_node.text.encode("ascii"), "změna váhy"))

    # Nové elementy smějí být jen nové assignmenty v cílové taxonomii.
    new_ids = current_ids - original_ids
    new_assignment_ids = []
    for ident in new_ids:
        node = current_elements[ident]
        if local_tag(node.tag) == "assignment":
            parent_id = current_parents.get(ident)
            if parent_id not in original_ids or not inside_target(original_paths[parent_id]):
                raise RuntimeError("Nové přiřazení neleží v cílové taxonomii; XML nebylo změněno.")
            new_assignment_ids.append(ident)
        else:
            # Potomci nového assignmentu jsou očekávaní; jiný nový uzel mimo něj odmítneme.
            ancestor = current_parents.get(ident)
            is_under_new_assignment = False
            while ancestor is not None:
                if ancestor in new_assignment_ids or (ancestor in new_ids and local_tag(current_elements[ancestor].tag) == "assignment"):
                    is_under_new_assignment = True
                    break
                ancestor = current_parents.get(ancestor)
            if not is_under_new_assignment:
                raise RuntimeError(f"Neočekávaně přibyl element {local_tag(node.tag)}; XML nebylo změněno.")

    # Vlož nové assignmenty po skupinách, aby se zachovalo odsazení a přehledná struktura.
    by_parent = defaultdict(list)
    for ident in new_assignment_ids:
        by_parent[current_parents[ident]].append(current_elements[ident])
    for parent_id, assignments in by_parent.items():
        parent = original_elements[parent_id]
        parent_path = original_paths[parent_id]
        if local_tag(parent.tag) != "assignments" or not inside_target(parent_path):
            raise RuntimeError("Nové přiřazení není uvnitř <assignments> cílové taxonomie; XML nebylo změněno.")
        _, _, close_start, _ = spans[parent_path]
        insert_at, close_indent = _line_indent(original_bytes, close_start)
        existing = [c for c in list(parent) if local_tag(c.tag) == "assignment"]
        if existing:
            child_path = original_paths[id(existing[0])]
            child_start = spans[child_path][0]
            _, assignment_indent = _line_indent(original_bytes, child_start)
            iv = first_child(existing[0], "investmentVehicle")
            if iv is not None:
                iv_start = spans[original_paths[id(iv)]][0]
                _, child_indent = _line_indent(original_bytes, iv_start)
            else:
                child_indent = assignment_indent + b"  "
        else:
            assignment_indent = close_indent + b"  "
            child_indent = assignment_indent + b"  "
        block = b"".join(_assignment_xml(a, assignment_indent, child_indent) for a in assignments)
        patches.append((insert_at, insert_at, block, "vložení nového assignmentu"))

    # Zpracování odzadu zachová všechny dříve vypočtené bajtové pozice.
    patches.sort(key=lambda p: (p[0], p[1]), reverse=True)
    result = original_bytes
    last_start = len(original_bytes) + 1
    for start, end, replacement, description in patches:
        if end > last_start:
            raise RuntimeError("Úpravy XML se překrývají; původní soubor nebyl změněn.")
        result = result[:start] + replacement + result[end:]
        last_start = start
    return result


def wrap_cell(value: str, width: int) -> list[str]:
    """Zalamuje text do pevné šířky bez ztráty znaků."""
    words = value.split()
    if not words:
        return [""]
    lines = []
    line = ""
    for word in words:
        while len(word) > width:
            if line:
                lines.append(line)
                line = ""
            lines.append(word[:width])
            word = word[width:]
        if not word:
            continue
        if not line:
            line = word
        elif len(line) + 1 + len(word) <= width:
            line += " " + word
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines or [""]


def print_text_table(rows):
    headers = ["Cenný papír", "Broker", "Kusy", "Původní %", "Nová %", "Akce"]
    widths = [35, 15, 12, 11, 11, 21]
    def render(cells):
        return " | ".join(str(value)[:width].ljust(width) for value, width in zip(cells, widths))
    print("\n" + render(headers))
    print("-" * (sum(widths) + 3 * (len(widths) - 1)))
    for row in rows:
        wrapped = [wrap_cell(str(value), width) for value, width in zip(row, widths)]
        for i in range(max(map(len, wrapped))):
            print(render([col[i] if i < len(col) else "" for col in wrapped]))

def build_parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in list(parent)}


def resolve_xml_reference(source: ET.Element, reference: str, parents: dict[ET.Element, ET.Element]) -> ET.Element | None:
    """Vyřeší běžnou relativní XML referenci Portfolio Performance (../.. a názvy elementů)."""
    current: ET.Element | None = source
    parts = [part for part in reference.split("/") if part not in ("", ".")]
    for part in parts:
        if current is None:
            return None
        if part == "..":
            current = parents.get(current)
        else:
            # Podporujeme i segmenty typu security[17].
            match = re.fullmatch(r"([^\[]+)(?:\[(\d+)\])?", part)
            if not match:
                return None
            name, index_text = match.groups()
            matches = [child for child in list(current) if local_tag(child.tag) == name]
            if index_text:
                idx = int(index_text) - 1
                current = matches[idx] if 0 <= idx < len(matches) else None
            else:
                current = matches[0] if matches else None
    return current


def broker_from_portfolio_name(portfolio_name: str) -> str:
    if portfolio_name in PORTFOLIO_TO_BROKER:
        return PORTFOLIO_TO_BROKER[portfolio_name]
    if portfolio_name.endswith(PORTFOLIO_SUFFIX):
        return portfolio_name[:-len(PORTFOLIO_SUFFIX)].strip()
    return portfolio_name.strip()


def run() -> int:
    path = Path(PORTFOLIO_FILE).expanduser().resolve()
    print("Přepočet taxonomie Portfolio Performance")
    print(f"Soubor: {path}")
    print(f"Taxonomie: {TAXONOMY_NAME}")
    print("Ujisti se, že je Portfolio Performance zavřené.")

    original_bytes, entries, zip_comment, xml_name = load_source(path)
    try:
        root = ET.fromstring(original_bytes)
    except ET.ParseError as exc:
        fail(f"XML se nepodařilo načíst; soubor nebude změněn: {exc}")

    # Uložíme původní strukturu a přesné bajtové rozsahy elementů. Zápis pak
    # upraví jen změněné váhy a přidaná/odstraněná přiřazení, nikoli celé XML.
    original_paths, original_parents, original_elements = map_element_paths(root)
    original_state = {ident: (node.tag, dict(node.attrib), node.text, node.tail)
                      for ident, node in original_elements.items()}
    raw_spans = index_xml_spans(original_bytes)

    securities_section = find_section(root, "securities")
    securities = children_named(securities_section, "security")
    if not securities:
        fail("V souboru nejsou žádné cenné papíry.")
    security_names = [find_child_text(s, "name") or f"Cenný papír {i}" for i, s in enumerate(securities, 1)]
    security_uuids = [find_child_text(s, "uuid") for s in securities]
    if any(not uid for uid in security_uuids) or len(set(security_uuids)) != len(security_uuids):
        fail("UUID cenných papírů chybí nebo se opakují; pro jistotu končím bez změn.")

    # Čteme POUZE skutečné portfolio-transaction přímo ze sekce portfolios.
    # Neprocházíme crossEntry a vnořené account-transaction: ty mohou obsahovat
    # vlastní shares=0 a nejsou samostatným pohybem kusů v portfoliu.
    holdings: dict[tuple[str, str], int] = defaultdict(int)
    history_pairs: set[tuple[str, str]] = set()
    unknown_types = []
    tx_type_counts = defaultdict(int)
    tx_type_audit = defaultdict(lambda: {"count": 0, "signed_shares": 0})
    tx_count = 0
    seen_tx_ids: set[str] = set()
    # V PP je sekce <portfolios> často jen seznam odkazů; vlastní objekty
    # portfolio jsou vložené do crossEntry. Bereme jen úplné definice (name,
    # uuid a transactions), nikoli referenční uzly bez obsahu.
    portfolio_nodes = []
    for node in root.iter():
        # Portfolio Performance může uložit plnou definici zdrojového portfolia
        # uvnitř <portfolioFrom>. Její seznam transakcí může obsahovat reference
        # na portfolioTransaction uvnitř hotovostních transakcí.
        if local_tag(node.tag) not in ("portfolio", "portfolioFrom"):
            continue
        if (find_child_text(node, "name") and find_child_text(node, "uuid")
                and first_child(node, "transactions") is not None):
            portfolio_nodes.append(node)
    print(f"Načteno XML; nalezeno definic portfolií: {len(portfolio_nodes)}.")
    xml_parents = build_parent_map(root)
    if not portfolio_nodes:
        fail("Nenašel jsem definice portfolií s vlastními transakcemi.")

    supported_signs = {
        "BUY": 1,
        "SELL": -1,
        "TRANSFER_IN": 1,
        "TRANSFER_OUT": -1,
        "DELIVERY_INBOUND": 1,
        "DELIVERY_OUTBOUND": -1,
    }
    for portfolio_node in portfolio_nodes:
        portfolio_name = find_child_text(portfolio_node, "name")
        if not portfolio_name:
            continue
        if portfolio_name in PORTFOLIO_TO_BROKER:
            broker = PORTFOLIO_TO_BROKER[portfolio_name]
        elif portfolio_name.endswith(PORTFOLIO_SUFFIX):
            broker = portfolio_name[:-len(PORTFOLIO_SUFFIX)].strip()
        else:
            # Názvy bez přípony se berou doslova; později se ověří, že existuje
            # odpovídající třída taxonomie. Případné výjimky patří do mapování výše.
            broker = portfolio_name.strip()
        if not broker:
            fail(f"Nepodařilo se určit brokera pro portfolio {portfolio_name!r}.")

        tx_container = first_child(portfolio_node, "transactions")
        if tx_container is None:
            continue
        # Pouze přímé děti kontejneru, nikdy vnořené reference/crossEntry.
        portfolio_transactions = [
            tx for tx in list(tx_container)
            if local_tag(tx.tag) == "portfolio-transaction"
        ]
        for tx_entry in portfolio_transactions:
            tx = tx_entry
            # Vnořené portfolioFrom může mít seznam referencí namísto úplných
            # transakcí. Vyřešíme referenci na portfolioTransaction v crossEntry.
            if tx.get("reference") and find_child_text(tx, "type") is None:
                resolved = resolve_xml_reference(tx, tx.get("reference", ""), xml_parents)
                if resolved is None:
                    fail(
                        f"Nelze vyřešit odkazovanou transakci {tx.get('reference')!r} "
                        f"v portfoliu {portfolio_name}; XML nebylo změněno."
                    )
                tx = resolved
            tx_id = find_child_text(tx, "uuid")
            if tx_id and tx_id in seen_tx_ids:
                continue
            if tx_id:
                seen_tx_ids.add(tx_id)
            tx_type = find_child_text(tx, "type")
            security_node = first_child(tx, "security")
            shares_text = find_child_text(tx, "shares")

            # Prázdné/neúplné XML uzly nejsou transakce; přeskočíme je jen tehdy,
            # když nemají ani typ, ani security, ani shares. Jinak je to chyba dat.
            if tx_type is None and security_node is None and shares_text is None:
                continue
            tx_count += 1
            if tx_type not in supported_signs:
                unknown_types.append((portfolio_name, tx_id, tx_type))
                continue
            if security_node is None or not security_node.get("reference"):
                fail(f"Portfolio transakce {tx_id or '(bez UUID)'} ({tx_type}) v {portfolio_name} nemá odkaz na cenný papír.")
            sec_index = parse_security_reference(security_node.get("reference", ""), securities) - 1
            try:
                shares = int(shares_text or "0")
            except ValueError:
                fail(f"Neplatná hodnota shares v portfolio transakci {tx_id or '(bez UUID)'}, portfolio {portfolio_name}.")
            if shares < 0:
                fail(f"Záporné shares v portfolio transakci {tx_id or '(bez UUID)'}, portfolio {portfolio_name}.")
            uid = security_uuids[sec_index]
            history_pairs.add((broker, uid))
            tx_type_counts[(broker, tx_type)] += 1
            tx_type_audit[(broker, uid, tx_type)]["count"] += 1
            tx_type_audit[(broker, uid, tx_type)]["signed_shares"] += shares * supported_signs[tx_type]
            holdings[(broker, uid)] += shares * supported_signs[tx_type]

    # U portfolio-transfer ukládá Portfolio Performance cílovou stranu převodu
    # jako vložený objekt <portfolioTo>, nikoli jako <portfolio>. Jeho přímá
    # TRANSFER_IN transakce proto v běžném průchodu portfolio_nodes chybí.
    # Doplníme pouze tyto vložené protistrany; UUID brání dvojímu započítání.
    for target_node in root.iter():
        if local_tag(target_node.tag) != "portfolioTo":
            continue
        target_name = find_child_text(target_node, "name")
        target_transactions = first_child(target_node, "transactions")
        if not target_name or target_transactions is None:
            continue
        if target_name in PORTFOLIO_TO_BROKER:
            target_broker = PORTFOLIO_TO_BROKER[target_name]
        elif target_name.endswith(PORTFOLIO_SUFFIX):
            target_broker = target_name[:-len(PORTFOLIO_SUFFIX)].strip()
        else:
            target_broker = target_name.strip()
        for tx in list(target_transactions):
            if local_tag(tx.tag) != "portfolio-transaction":
                continue
            tx_id = find_child_text(tx, "uuid")
            if tx_id and tx_id in seen_tx_ids:
                continue
            if tx_id:
                seen_tx_ids.add(tx_id)
            tx_type = find_child_text(tx, "type")
            security_node = first_child(tx, "security")
            shares_text = find_child_text(tx, "shares")
            if tx_type is None and security_node is None and shares_text is None:
                continue
            tx_count += 1
            if tx_type not in supported_signs:
                unknown_types.append((target_name, tx_id, tx_type))
                continue
            if security_node is None or not security_node.get("reference"):
                fail(f"Vložená cílová portfolio transakce {tx_id or '(bez UUID)'} ({tx_type}) v {target_name} nemá odkaz na cenný papír.")
            sec_index = parse_security_reference(security_node.get("reference", ""), securities) - 1
            try:
                shares = int(shares_text or "0")
            except ValueError:
                fail(f"Neplatná hodnota shares v cílové portfolio transakci {tx_id or '(bez UUID)'}, portfolio {target_name}.")
            if shares < 0:
                fail(f"Záporné shares v cílové portfolio transakci {tx_id or '(bez UUID)'}, portfolio {target_name}.")
            uid = security_uuids[sec_index]
            history_pairs.add((target_broker, uid))
            tx_type_counts[(target_broker, tx_type)] += 1
            tx_type_audit[(target_broker, uid, tx_type)]["count"] += 1
            tx_type_audit[(target_broker, uid, tx_type)]["signed_shares"] += shares * supported_signs[tx_type]
            holdings[(target_broker, uid)] += shares * supported_signs[tx_type]

    # V8: Zpracuj i zdrojovou stranu portfolio-transfer uloženou vnořeně
    # jako crossEntry/transactionFrom. Některé exporty mají typ TRANSFER_OUT
    # výslovně uvedený, v jiných je třeba opačný typ odvodit z TRANSFER_IN.
    # Záznamy identifikujeme podle UUID a započítáme zdrojovou stranu nejvýše jednou.
    nested_source_ids: set[str] = set()
    source_transfer_count = 0
    for tx in root.iter():
        if local_tag(tx.tag) != "portfolio-transaction":
            continue
        cross = first_child(tx, "crossEntry")
        if cross is None or cross.get("class") != "portfolio-transfer":
            continue
        transaction_from = first_child(cross, "transactionFrom")
        portfolio_from = first_child(cross, "portfolioFrom")
        if transaction_from is None or portfolio_from is None:
            continue
        # transactionFrom může být jen reference na skutečnou transakci
        # uvedenou v seznamu portfolioFrom/transactions.
        if transaction_from.get("reference") and find_child_text(transaction_from, "type") is None:
            resolved_from = resolve_xml_reference(
                transaction_from, transaction_from.get("reference", ""), xml_parents
            )
            if resolved_from is None:
                fail(
                    f"Nelze vyřešit zdrojovou transakci {transaction_from.get('reference')!r}; "
                    f"XML nebylo změněno."
                )
            transaction_from = resolved_from
        source_tx_id = find_child_text(transaction_from, "uuid")
        if source_tx_id and (source_tx_id in nested_source_ids or source_tx_id in seen_tx_ids):
            # Zdrojová transakce už byla započítána přes úplnou definici
            # portfolioFrom (nebo byla zpracována při předchozím převodu).
            continue
        # Zdrojové portfolio určujeme pouze podle reference portfolioFrom,
        # nikoli podle podobnosti názvu cenného papíru nebo částky.
        source_portfolio = resolve_xml_reference(portfolio_from, portfolio_from.get("reference", ""), xml_parents)
        source_name = find_child_text(source_portfolio, "name") if source_portfolio is not None else None
        if not source_name:
            # Pokud nelze vazbu bezpečně vyřešit, raději skončíme než odhadovat účet.
            fail(f"Nelze bezpečně určit zdrojové portfolio pro převod {source_tx_id or '(bez UUID)'}; XML nebylo změněno.")
        source_broker = broker_from_portfolio_name(source_name)
        if not source_broker:
            fail(f"Prázdný název zdrojového brokera u převodu {source_tx_id or '(bez UUID)' }.")
        outer_type = find_child_text(tx, "type")
        source_type = find_child_text(transaction_from, "type")
        if source_type not in ("TRANSFER_OUT", "TRANSFER_IN"):
            # Přesně opačný typ než typ na vnější straně převodu.
            if outer_type == "TRANSFER_IN":
                source_type = "TRANSFER_OUT"
            elif outer_type == "TRANSFER_OUT":
                source_type = "TRANSFER_IN"
            else:
                fail(f"U převodu {source_tx_id or '(bez UUID)'} nelze odvodit opačný typ z {outer_type!r}; XML nebylo změněno.")
        source_security = first_child(transaction_from, "security")
        if source_security is None or not source_security.get("reference"):
            # Někdy může zdrojová strana dědit odkaz na cenný papír z vnější transakce.
            source_security = first_child(tx, "security")
        if source_security is None or not source_security.get("reference"):
            fail(f"Zdrojová strana převodu {source_tx_id or '(bez UUID)'} nemá odkaz na cenný papír.")
        sec_index = parse_security_reference(source_security.get("reference", ""), securities) - 1
        source_shares_text = find_child_text(transaction_from, "shares") or find_child_text(tx, "shares")
        try:
            source_shares = int(source_shares_text or "0")
        except ValueError:
            fail(f"Neplatná hodnota shares ve zdrojové straně převodu {source_tx_id or '(bez UUID)'}.")
        if source_shares < 0:
            fail(f"Záporné shares ve zdrojové straně převodu {source_tx_id or '(bez UUID)'}.")
        uid = security_uuids[sec_index]
        sign = supported_signs[source_type]
        # Pokud zdrojová transakce už byla načtena jako přímá transakce,
        # její UUID v seen_tx_ids znamená, že ji znovu nepřičítáme.
        # Vnořené transactionFrom běžný průchod nezpracovává, proto UUID
        # do seen_tx_ids samo o sobě není důvodem k přeskočení.
        if source_tx_id:
            nested_source_ids.add(source_tx_id)
        history_pairs.add((source_broker, uid))
        tx_type_counts[(source_broker, source_type)] += 1
        tx_type_audit[(source_broker, uid, source_type)]["count"] += 1
        tx_type_audit[(source_broker, uid, source_type)]["signed_shares"] += source_shares * sign
        holdings[(source_broker, uid)] += source_shares * sign
        source_transfer_count += 1

    if source_transfer_count:
        print(f"Doplněny vnořené zdrojové strany portfolio-transfer: {source_transfer_count}.")

    if unknown_types:
        details = "; ".join(f"{p}: {t or 'chybí typ'} ({uid or 'bez UUID'})" for p, uid, t in unknown_types[:12])
        fail("Našel jsem nepodporovaný typ skutečné portfolio transakce. Bezpečně končím, aby nebyl počet kusů chybný: " + details)
    if tx_count == 0:
        fail("Nenašel jsem žádné portfolio transakce se záznamem o cenném papíru.")

    # Ověř, že se žádný broker nedostane do záporného počtu kusů.
    for (broker, uid), amount in holdings.items():
        if amount < 0:
            name = security_names[security_uuids.index(uid)]
            fail(f"Po výpočtu vyšel záporný počet kusů: {name} u {broker}. Zkontroluj mapování PORTFOLIO_TO_BROKER a převody mezi portfolii. Změny nebyly provedeny.")

    taxonomies = find_section(root, "taxonomies")
    targets = [t for t in children_named(taxonomies, "taxonomy") if find_child_text(t, "name") == TAXONOMY_NAME]
    if len(targets) != 1:
        fail(f"Očekával jsem právě jednu taxonomii „{TAXONOMY_NAME}“, našel jsem {len(targets)}.")
    taxonomy = targets[0]
    print("Taxonomie cílového brokera nalezena; ověřuji přiřazení cenných papírů a počítám nové váhy...")
    root_class = first_child(taxonomy, "root")
    # children obsahuje přímo uzly classification.
    root_children = first_child(root_class, "children") if root_class is not None else None
    broker_classes = [el for el in (list(root_children) if root_children is not None else []) if local_tag(el.tag) == "classification"]
    classes_by_name = {find_child_text(c, "name"): c for c in broker_classes}
    if len(classes_by_name) != len(broker_classes):
        fail("V taxonomii jsou duplicitní názvy brokerů.")

    # Mapa indexů cenných papírů podle UUID.
    index_by_uuid = {uid: i + 1 for i, uid in enumerate(security_uuids)}
    # Vezmi šablonu relativní cesty z již existujícího přiřazení cenného papíru.
    ref_template = None
    for cls in broker_classes:
        assigns = first_child(cls, "assignments")
        if assigns is None:
            continue
        for ass in children_named(assigns, "assignment"):
            iv = first_child(ass, "investmentVehicle")
            if iv is not None and iv.get("class") == "security":
                ref_template = iv.get("reference")
                break
        if ref_template:
            break
    if not ref_template:
        fail("Nenašel jsem existující odkaz na cenný papír v taxonomii; nelze bezpečně vytvořit nová přiřazení.")
    ref_prefix = re.sub(r"/securities/security(?:\[\d+\])?$", "/securities/security", ref_template)

    # Držení pro brokery bez odpovídající třídy by jinak zůstala nezařazená.
    broker_names_with_holdings = sorted({broker for (broker, uid), amount in holdings.items() if amount > 0})
    missing_classes = [broker for broker in broker_names_with_holdings if broker not in classes_by_name]
    if missing_classes:
        fail("Pro tato portfolia není odpovídající třída v taxonomii „Podle brokera“: " + ", ".join(missing_classes) + ". Doplň jejich mapování do PORTFOLIO_TO_BROKER na začátku skriptu.")

    # Souhrn aktuálních kladných pozic podle brokera a cenného papíru.
    shares_by_security: dict[str, dict[str, int]] = defaultdict(dict)
    for (broker, uid), amount in holdings.items():
        if amount > 0:
            shares_by_security[uid][broker] = amount

    # Před změnou uložíme původní přiřazení pro report.
    old_assignments: dict[tuple[str, str], int] = {}
    changes = []
    security_assignments_removed = []
    security_assignments_preserved_without_history = []
    for broker, cls in classes_by_name.items():
        assignments = first_child(cls, "assignments")
        if assignments is None:
            assignments = ET.SubElement(cls, "assignments")
        for ass in list(children_named(assignments, "assignment")):
            idx = resolve_vehicle_index(ass, securities)
            if idx is None:
                continue  # účty/hotovost a jiné typy investičních vozidel se nemění
            uid = security_uuids[idx - 1]
            weight_text = find_child_text(ass, "weight")
            try:
                old_weight = int(weight_text or "0")
            except ValueError:
                fail(f"Neplatná váha přiřazení pro {security_names[idx-1]} u {broker}.")
            key = (broker, uid)
            if key in old_assignments:
                fail(f"Duplicitní přiřazení {security_names[idx-1]} u {broker}; nejdřív je potřeba vyřešit duplicitu.")
            old_assignments[key] = old_weight

    # Pro každé existující držení nastav váhy; chybějící přiřazení vytvoř.
    for uid, broker_shares in shares_by_security.items():
        weights = round_weights(broker_shares)
        sec_name = security_names[security_uuids.index(uid)]
        for broker, new_weight in weights.items():
            old_weight = old_assignments.get((broker, uid))
            changes.append({"security": sec_name, "uuid": uid, "broker": broker, "old": old_weight, "new": new_weight,
                            "shares": broker_shares[broker], "created": old_weight is None})

    # Změň existující váhy a odstraň zastaralá security přiřazení (pozice už není držena).
    for broker, cls in classes_by_name.items():
        assignments = first_child(cls, "assignments")
        for ass in list(children_named(assignments, "assignment")):
            idx = resolve_vehicle_index(ass, securities)
            if idx is None:
                continue
            uid = security_uuids[idx - 1]
            if uid in shares_by_security and broker not in shares_by_security[uid]:
                assignments.remove(ass)
                security_assignments_removed.append((security_names[idx - 1], broker, old_assignments.get((broker, uid))))
            elif uid in shares_by_security and broker in shares_by_security[uid]:
                set_child_text(ass, "weight", str(round_weights(shares_by_security[uid])[broker]))
            elif (broker, uid) in history_pairs:
                # Historie tohoto brokeru dokládá nulový zůstatek (např. vše prodáno).
                assignments.remove(ass)
                security_assignments_removed.append((security_names[idx - 1], broker, old_assignments.get((broker, uid))))
            else:
                # Samotná absence transakce není důkazem nulového držení.
                security_assignments_preserved_without_history.append((security_names[idx - 1], broker, old_assignments.get((broker, uid))))

    # Přidej chybějící security přiřazení. Ostatní assignmenty včetně hotovostních necháváme beze změny.
    for change in changes:
        if not change["created"]:
            continue
        broker = change["broker"]
        uid = change["uuid"]
        cls = classes_by_name[broker]
        assignments = first_child(cls, "assignments")
        new_ass = ET.SubElement(assignments, "assignment")
        iv = ET.SubElement(new_ass, "investmentVehicle", {"class": "security", "reference": ref_prefix + f"[{index_by_uuid[uid]}]"})
        ET.SubElement(new_ass, "weight").text = str(change["new"])
        # Rank na konci seznamu. PP používá u některých tříd MAX_INT jako pořadí „na konec“.
        existing_ranks = []
        for ass in children_named(assignments, "assignment"):
            rank = find_child_text(ass, "rank")
            if rank and rank.isdigit():
                existing_ranks.append(int(rank))
        rank_value = (max(existing_ranks) + 1) if existing_ranks and max(existing_ranks) < 2_147_483_647 else 2_147_483_647
        ET.SubElement(new_ass, "rank").text = str(rank_value)

    # Ujisti se, že součet vah pro každý držený security je přesně 10000.
    for uid, broker_shares in shares_by_security.items():
        total = 0
        for broker in broker_shares:
            cls = classes_by_name[broker]
            assigns = first_child(cls, "assignments")
            found = []
            for ass in children_named(assigns, "assignment"):
                if resolve_vehicle_index(ass, securities) == index_by_uuid[uid]:
                    found.append(ass)
            if len(found) != 1:
                fail(f"Po úpravě není právě jedno přiřazení pro {security_names[security_uuids.index(uid)]} u {broker}.")
            total += int(find_child_text(found[0], "weight") or "0")
        if total != WEIGHT_TOTAL:
            fail(f"Součet vah pro {security_names[security_uuids.index(uid)]} není 100 % (je {total}).")

    # Ověř, že mimo cílovou taxonomii nezměníme žádná XML data.
    print("Kontroluji, zda se změnila pouze cílová taxonomie...")
    try:
        new_xml = apply_minimal_xml_patches(original_bytes, root, original_state,
                                            original_paths, original_parents,
                                            original_elements, raw_spans, taxonomy)
        check_root = ET.fromstring(new_xml)
        old_root = ET.fromstring(original_bytes)
    except Exception as exc:
        fail(f"Nové XML se nepodařilo bezpečně sestavit nebo ověřit: {exc}")
    if canonical_without_target_taxonomy(old_root, TAXONOMY_NAME) != canonical_without_target_taxonomy(check_root, TAXONOMY_NAME):
        print("\nDiagnostika rozdílů mimo cílovou taxonomii:", file=sys.stderr)
        differences = find_xml_differences(old_root, check_root, TAXONOMY_NAME)
        if differences:
            for difference in differences:
                print(f"  - {difference}", file=sys.stderr)
        else:
            print("  Strukturální rozdíl nebyl nalezen; rozdíl může být pouze v serializaci XML.", file=sys.stderr)
        fail("Kontrola zjistila změnu mimo cílovou taxonomii. Původní soubor zůstane beze změny.")
    print("Kontrola v pořádku: mimo cílovou taxonomii nebyly zjištěny změny.")

    # Vypiš report před jakýmkoli zápisem.
    print(f"\nZkontrolováno portfolio transakcí: {tx_count}")
    print("Výpočet: BUY/TRANSFER_IN/DELIVERY_INBOUND přičítám, SELL/TRANSFER_OUT/DELIVERY_OUTBOUND odečítám. U portfolio-transfer se zpracuje také propojená vnořená zdrojová strana; chybějící opačný typ se odvodí jen z vazby crossEntry. Vnořené hotovostní transakce ignoruji.")
    transfer_counts = [(broker, kind, count) for (broker, kind), count in sorted(tx_type_counts.items())
                       if kind in ("TRANSFER_IN", "TRANSFER_OUT", "DELIVERY_INBOUND", "DELIVERY_OUTBOUND")]
    if transfer_counts:
        print("Zachycené převody podle portfolia:")
        for broker, kind, count in transfer_counts:
            print(f"  {broker}: {kind} – {count} transakcí")
    else:
        print("Upozornění: v procházené historii nebyly nalezeny typy TRANSFER_IN/OUT ani DELIVERY_INBOUND/OUTBOUND. Pokud byly cenné papíry mezi brokery převáděny, zkontroluj, jak jsou převody v Portfolio Performance zaznamenané.")
    affected_uids = {c["uuid"] for c in changes if c["created"] or c["old"] != c["new"]}
    if affected_uids:
        print("Kontrola historie u cenných papírů s novým přiřazením nebo změnou váhy:")
        for uid in sorted(affected_uids, key=lambda u: security_names[security_uuids.index(u)].casefold()):
            print(f"  {security_names[security_uuids.index(uid)]}:")
            rows = [(broker, kind, values) for (broker, security_uid, kind), values in tx_type_audit.items() if security_uid == uid]
            if not rows:
                print("    bez zaznamenaných transakcí")
            for broker, kind, values in sorted(rows, key=lambda item: (item[0].casefold(), item[1])):
                signed = values["signed_shares"] / SHARES_SCALE
                print(f"    {broker}: {kind}, {values['count']}×, čistý příspěvek {format_share_value(signed) if signed < 0 else '+' + format_share_value(signed)} kusů")
    if changes:
        table_rows = []
        for c in sorted(changes, key=lambda x: (x['security'].casefold(), x['broker'].casefold())):
            old = "— (nové)" if c["old"] is None else f"{c['old']/100:.2f}%"
            action = "nové přiřazení" if c["created"] else ("beze změny" if c["old"] == c["new"] else "upravit váhu")
            table_rows.append([c['security'], c['broker'], format_share_value(c['shares']/SHARES_SCALE), old, f"{c['new']/100:.2f}%", action])
        print_text_table(table_rows)
    if security_assignments_removed:
        print("\nOdstraněná přiřazení bez aktuální pozice:")
        for name, broker, old in sorted(security_assignments_removed):
            print(f"  {name} | {broker} | původně {old/100:.2f}%" if old is not None else f"  {name} | {broker}")
    else:
        print("\nŽádná zastaralá přiřazení cenných papírů nebyla odstraněna.")
    if security_assignments_preserved_without_history:
        print("\nPonechaná přiřazení bez historie transakcí (skript z opatrnosti neodhadoval nulový zůstatek):")
        for name, broker, old in sorted(security_assignments_preserved_without_history):
            print(f"  {name} | {broker} | váha {old/100:.2f}%" if old is not None else f"  {name} | {broker}")
    if not changes and not security_assignments_removed:
        print("\nTaxonomie už odpovídá vypočteným pozicím; změny nejsou potřeba.")

    answer = input("\nChceš uložit změny do původního souboru? Napiš přesně ANO: ").strip()
    if answer != "ANO":
        print("Zrušeno. Původní soubor nebyl změněn a záloha nebyla vytvořena.")
        return 0

    # Vytvoř a ověř dočasný výstup ještě před zálohou a přepsáním originálu.
    temp_path = write_temp(path, xml_name, entries, zip_comment, new_xml)
    try:
        # Kontrola archivu/ XML po zapsání dočasného souboru.
        temp_xml, _, _, _ = load_source(temp_path)
        ET.fromstring(temp_xml)
        if entries is not None:
            with zipfile.ZipFile(temp_path, "r") as zf:
                bad_member = zf.testzip()
                if bad_member:
                    fail(f"Kontrola ZIP selhala na souboru {bad_member}; originál nebyl změněn.")
        # Záloha je přesná kopie původních bajtů.
        backup = backup_name(path, dt.datetime.now())
        if backup.exists():
            # Kolize je velmi nepravděpodobná, ale nepřepisujeme starší zálohu.
            backup = backup_name(path, dt.datetime.now() + dt.timedelta(seconds=1))
        shutil.copy2(path, backup)
        # Atomická výměna na stejném disku; pokud selže, originál zůstane nedotčen.
        os.replace(temp_path, path)
        deleted = prune_backups(path, BACKUPS_TO_KEEP)
        print(f"\nHotovo. Upravený soubor: {path}")
        print(f"Záloha: {backup}")
        print(f"Počet ponechaných záloh: {min(BACKUPS_TO_KEEP, len([p for p in path.parent.iterdir() if p.is_file() and p.name.startswith(path.stem + BACKUP_MARKER)]))}")
        if deleted:
            print("Smazané starší zálohy:")
            for p in deleted:
                print(f"  {p.name}")
    finally:
        temp_path.unlink(missing_ok=True)
    return 0


class Tee:
    """Zapisuje výstup současně do konzole a do logovacího souboru."""
    def __init__(self, console, log_file):
        self.console = console
        self.log_file = log_file

    def write(self, text):
        self.console.write(text)
        self.log_file.write(text)
        self.flush()
        return len(text)

    def flush(self):
        self.console.flush()
        self.log_file.flush()

    def isatty(self):
        return self.console.isatty()

    @property
    def encoding(self):
        return getattr(self.console, "encoding", "utf-8")


def create_log_path() -> Path:
    """Název logu odvodí od nastavené cesty k portfoliu a aktuálního času."""
    source = Path(PORTFOLIO_FILE).expanduser()
    folder = source.parent
    stamp = dt.datetime.now().strftime("%Y.%m.%d_%H-%M.%S")
    return folder / f"{source.stem}{LOG_SUFFIX}.{stamp}.txt"


if __name__ == "__main__":
    original_stdout, original_stderr = sys.stdout, sys.stderr
    try:
        log_path = create_log_path()
        log_file = log_path.open("w", encoding="utf-8", newline="")
    except OSError as exc:
        print(f"UPOZORNĚNÍ: Log se nepodařilo vytvořit: {exc}", file=sys.stderr)
        try:
            raise SystemExit(run())
        except (RuntimeError, OSError, zipfile.BadZipFile, ET.ParseError) as run_exc:
            print(f"\nCHYBA: {run_exc}", file=sys.stderr)
            print("Původní soubor nebyl přepsán, pokud chyba nastala před atomickou výměnou.", file=sys.stderr)
            raise SystemExit(1)
    else:
        try:
            sys.stdout = Tee(original_stdout, log_file)
            sys.stderr = Tee(original_stderr, log_file)
            print(f"Log se ukládá do: {log_path}")
            try:
                raise SystemExit(run())
            except (RuntimeError, OSError, zipfile.BadZipFile, ET.ParseError) as exc:
                print(f"\nCHYBA: {exc}", file=sys.stderr)
                print("Původní soubor nebyl přepsán, pokud chyba nastala před atomickou výměnou.", file=sys.stderr)
                raise SystemExit(1)
        finally:
            sys.stdout, sys.stderr = original_stdout, original_stderr
            log_file.close()
