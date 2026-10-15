"""Générateur PDF minimal pour les tests (texte Helvetica, une liste de lignes par page) : aucune dépendance."""


def make_pdf(pages: list[list[str]]) -> bytes:
    objects: list[bytes] = []

    def esc(line: str) -> bytes:
        return line.encode("cp1252", "replace").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")

    font_id = 3
    page_ids, content_ids = [], []
    n = 4
    for _ in pages:
        page_ids.append(n)
        content_ids.append(n + 1)
        n += 2
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [" + b" ".join(f"{p} 0 R".encode() for p in page_ids) + b"] /Count " + str(len(pages)).encode() + b" >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for lines, pid, cid in zip(pages, page_ids, content_ids):
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {cid} 0 R >>".encode())
        stream = b"BT /F1 9 Tf 40 800 Td 12 TL " + b" ".join(b"(" + esc(line) + b") Tj T*" for line in lines) + b" ET"
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(out)


def kid_lines(isin: str, name: str, sri: int = 3, ongoing: str = "1,35", transaction: str = "0,12", entry: str = "2,00") -> list[list[str]]:
    return [[
        "Document d'informations clés",
        f"Produit : {name} - ISIN : {isin}",
        "Initiateur : Société de Gestion Fictive. Ce document est exact et à jour au 15/02/2026.",
        "Objectifs : le fonds vise une performance supérieure à son indicateur sur la durée de placement (texte fictif).",
        "Investisseurs de détail visés : tous investisseurs.",
        f"Indicateur de risque : nous avons classé ce produit dans la classe de risque {sri} sur 7.",
        "Période de détention recommandée : 5 ans",
    ], [
        "Composition des coûts",
        f"Coûts d'entrée {entry} % du montant que vous payez au moment de l'entrée dans l'investissement.",
        "Coûts de sortie Nous ne facturons pas de coûts de sortie pour ce produit.",
        f"Frais de gestion et autres frais administratifs et d'exploitation {ongoing} % de la valeur de votre investissement par an.",
        f"Coûts de transaction {transaction} % de la valeur de votre investissement par an.",
        "Commissions liées aux résultats Aucune commission liée aux résultats n'existe pour ce produit.",
    ]]
