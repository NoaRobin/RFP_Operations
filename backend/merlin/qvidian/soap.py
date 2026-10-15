"""SOAP 1.1 minimal pour les services web Qvidian (Qvidian.asmx, QvidianAuthentication.asmx).

Pas de dépendance SOAP : l'enveloppe est écrite à la main dans l'ordre du WSDL (WSDL/Qvidian.wsdl du paquet
qpa_Oct26_consolidated) et la réponse est lue en dictionnaires. Espace de noms : http://qvidian.com/webservices/.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from xml.sax.saxutils import escape

NS = "http://qvidian.com/webservices/"
SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"


@dataclass
class Items:
    """Tableau « ArrayOfX » : <tag>v1</tag><tag>v2</tag>… (ex. Items("int", [1, 2]), Items("string", ["a"]))."""
    tag: str
    values: list[Any]


@dataclass
class Typed:
    """Élément polymorphe (xsi:type), ex. Typed("QueryFilterString", {...}) pour projectSearch."""
    xsi_type: str
    fields: dict[str, Any]


class SoapFault(Exception):
    """Erreur renvoyée par Qvidian : <Error><Number/><Message/><Source/><Type/></Error> dans le détail du fault."""

    def __init__(self, message: str, number: str = "", source: str = "", kind: str = "", code: str = ""):
        super().__init__(message)
        self.message, self.number, self.source, self.kind, self.code = message, number, source, kind, code


def _value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return f"{value.isoformat()}T00:00:00"
    return escape(str(value))


def write(name: str, value: Any) -> str:
    """Un élément XML (sans préfixe : l'espace de noms par défaut est hérité de l'opération)."""
    if value is None:
        return f'<{name} xsi:nil="true" />'
    if isinstance(value, Items):
        return f"<{name}>{''.join(write(value.tag, v) for v in value.values)}</{name}>"
    if isinstance(value, Typed):
        return f'<{name} xsi:type="{value.xsi_type}">{"".join(write(k, v) for k, v in value.fields.items())}</{name}>'
    if isinstance(value, dict):
        return f"<{name}>{''.join(write(k, v) for k, v in value.items())}</{name}>"
    if isinstance(value, RawXml):
        return value.xml
    return f"<{name}>{_value(value)}</{name}>"


@dataclass
class RawXml:
    """Fragment déjà sérialisé (ex. requête renvoyée par librarySearchRequestInit puis ajustée)."""
    xml: str


def envelope(operation: str, params: dict[str, Any], header: dict[str, Any] | None) -> bytes:
    head = ""
    if header is not None:
        head = f'<soap:Header><QvidianCredentialHeader xmlns="{NS}">{"".join(write(k, v) for k, v in header.items())}</QvidianCredentialHeader></soap:Header>'
    body = "".join(write(k, v) for k, v in params.items())
    xml = (f'<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap="{SOAP_ENV}" xmlns:xsi="{XSI}" '
           f'xmlns:xsd="http://www.w3.org/2001/XMLSchema">{head}<soap:Body><{operation} xmlns="{NS}">{body}</{operation}></soap:Body></soap:Envelope>')
    return xml.encode("utf-8")


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def to_py(elem: ET.Element) -> Any:
    """Élément → str | dict | None ; les enfants répétés deviennent des listes (voir `as_list`)."""
    if elem.get(f"{{{XSI}}}nil") == "true":
        return None
    children = list(elem)
    if not children:
        return elem.text if elem.text is not None else ""
    out: dict[str, Any] = {}
    for child in children:
        key, val = local(child.tag), to_py(child)
        if key in out:
            if not isinstance(out[key], list) or not getattr(out[key], "_repeated", False):
                out[key] = _Repeated([out[key]])
            out[key].append(val)
        else:
            out[key] = val
    return {k: list(v) if isinstance(v, _Repeated) else v for k, v in out.items()}


class _Repeated(list):
    _repeated = True


def as_list(value: Any, tag: str | None = None) -> list[Any]:
    """Tableau SOAP lu par `to_py` : {"Content": {...}} ou {"Content": [{...}, …]} → liste."""
    if value is None or value == "":
        return []
    if tag is not None and isinstance(value, dict):
        value = value.get(tag)
        if value is None:
            return []
    return value if isinstance(value, list) else [value]


def parse(content: bytes, operation: str) -> ET.Element:
    """Renvoie l'élément <operationResponse> ; lève SoapFault si Qvidian a répondu une erreur."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise SoapFault(f"réponse illisible ({error})", kind="xml") from error
    body = next((e for e in root if local(e.tag) == "Body"), None)
    if body is None:
        raise SoapFault("réponse sans corps SOAP", kind="xml")
    for child in body:
        name = local(child.tag)
        if name == "Fault":
            fault = {local(e.tag): e for e in child.iter()}
            code = (fault.get("faultcode").text or "") if fault.get("faultcode") is not None else ""
            text = (fault.get("faultstring").text or "") if fault.get("faultstring") is not None else ""
            err = fault.get("Error")
            if err is not None:
                parts = {local(e.tag): (e.text or "") for e in err}
                raise SoapFault(parts.get("Message") or text, parts.get("Number", ""), parts.get("Source", ""), parts.get("Type", ""), code)
            raise SoapFault(text or "erreur Qvidian", code=code)
        if name == f"{operation}Response":
            return child
    raise SoapFault(f"réponse inattendue (pas de {operation}Response)", kind="xml")


def result(content: bytes, operation: str) -> Any:
    """Valeur de <operationResult> (ou dictionnaire de tous les paramètres de sortie s'il y en a plusieurs)."""
    resp = to_py(parse(content, operation))
    if not isinstance(resp, dict):
        return None
    key = f"{operation}Result"
    if key in resp and len(resp) == 1:
        return resp[key]
    return resp


def element_xml(elem: ET.Element, name: str) -> str:
    """Ré-écrit un élément reçu sous un autre nom, sans préfixes (pour renvoyer une requête initialisée par le serveur)."""
    def inner(e: ET.Element, tag: str) -> str:
        attrs = ' xsi:nil="true"' if e.get(f"{{{XSI}}}nil") == "true" else ""
        kids = list(e)
        if not kids:
            return f"<{tag}{attrs}>{escape(e.text or '')}</{tag}>"
        return f"<{tag}{attrs}>{''.join(inner(k, local(k.tag)) for k in kids)}</{tag}>"
    return inner(elem, name)


def set_child(parent: ET.Element, name: str, order: list[str]) -> ET.Element:
    """Enfant `name` de `parent` (créé à sa place dans l'ordre du WSDL s'il manque)."""
    for child in parent:
        if local(child.tag) == name:
            return child
    new = ET.Element(name)
    rank = order.index(name) if name in order else len(order)
    position = len(parent)
    for i, child in enumerate(list(parent)):
        if local(child.tag) in order and order.index(local(child.tag)) > rank:
            position = i
            break
    parent.insert(position, new)
    return new


def set_value(parent: ET.Element, name: str, value: Any, order: list[str]) -> None:
    node = set_child(parent, name, order)
    for k in list(node):
        node.remove(k)
    node.attrib.pop(f"{{{XSI}}}nil", None)
    if isinstance(value, Items):
        node.text = None
        for v in value.values:
            sub = ET.SubElement(node, value.tag)
            sub.text = _raw(v)
    else:
        node.text = _raw(value)


def _raw(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


# Ordre des champs (WSDL) des types modifiés après librarySearchRequestInit
ORDER = {
    "LibrarySearchRequest": ["searchRequestUniqueID", "searchResultsCacheID", "searchSettingsID", "searchSettingsRevision", "systemSearchType",
                             "searchTitle", "searchDescription", "resetResultsCache", "updateSortOrder", "resultsAsList", "searchTermsCriteria",
                             "searchCriteria", "cmSelectFields"],
    "searchTermsCriteria": ["terms", "useInflectional", "defaultBehavior", "foundInFields", "languageIDs", "useSuggestedSearch",
                            "useAlternativeSearchTermsParsing"],
    "SearchCriteria": ["maxResults", "pageSize", "pageIndex", "filtersAND", "filtersOR", "searchFields", "quickSearch", "quickSearchFields",
                       "offset", "sortField", "sortDesc", "loadData", "loadRequiredData", "requiredFields", "requiredPageSize",
                       "columnDefinitions", "compressData", "compressRequiredData"],
}
# Ordre complet de ContentUpdates (libraryContentDetailsUpdate) : chaque champ a son drapeau « …Updated »
CONTENT_UPDATES = ["AlertEnabled", "AlertEnabledUpdated", "AlertText", "AlertTextUpdated", "Comments", "CommentsUpdated", "ContactInfo",
                   "ContactInfoUpdated", "ContentFileDesc", "ContentFileDescUpdated", "ContentFileFormat", "ContentFileFormatUpdated",
                   "ContentFilename", "ContentFilenameUpdated", "ContentText", "ContentTextUpdated", "ContentType", "ContentTypeUpdated",
                   "DateToExpire", "DateToExpireUpdated", "Enabled", "EnabledUpdated", "InLineEdit", "InLineEditUpdated", "KeywordIDs",
                   "KeywordIDsUpdated", "LCID", "LCIDUpdated", "LearnedTerms", "LearnedTermsUpdated", "LibraryFolderID",
                   "LibraryFolderIDUpdated", "OwnerIDs", "OwnersIDsUpdated", "Password", "PasswordUpdated", "ProjectRestrictions",
                   "ProjectRestrictionsUpdated", "Title", "TitleUpdated", "ContentCustomX", "ContentCustomXUpdated"]
# Champs obligatoires (minOccurs=1) de ContentUpdates et leur valeur neutre quand on ne les modifie pas
CONTENT_UPDATES_DEFAULTS = {"AlertEnabled": False, "ContentType": "NotSet", "DateToExpire": None, "Enabled": False, "InLineEdit": False,
                            "LCID": 0, "LibraryFolderID": 0, "ProjectRestrictions": "None"}


def content_updates(changes: dict[str, Any]) -> dict[str, Any]:
    """{"Enabled": False} → ContentUpdates complet, dans l'ordre, avec EnabledUpdated=true et tous les autres drapeaux à false."""
    out: dict[str, Any] = {}
    for name in CONTENT_UPDATES:
        if name.endswith("Updated"):
            field_name = "OwnerIDs" if name == "OwnersIDsUpdated" else name[: -len("Updated")]
            out[name] = field_name in changes
        elif name in changes:
            out[name] = changes[name]
        elif name in CONTENT_UPDATES_DEFAULTS:
            out[name] = CONTENT_UPDATES_DEFAULTS[name]
    return out


__all__ = ["Items", "Typed", "RawXml", "SoapFault", "envelope", "parse", "result", "to_py", "as_list", "element_xml", "set_child", "set_value",
           "ORDER", "content_updates", "NS", "local"]
