"""PDF case report (ReportLab): every statement is generated from computed data and cites record ids."""
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak


def build_pdf(S, eid=None):
    A, M, R, alerts = S["A"], S["M"], S["risk"], S["alerts"]
    ss = getSampleStyleSheet()
    H1, H2, B = ss["Title"], ss["Heading2"], ParagraphStyle("b", parent=ss["BodyText"], fontSize=9, leading=12)
    small = ParagraphStyle("s", parent=B, fontSize=8, textColor=colors.grey)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title="Criminal Network Analysis - Case Report")
    st = []

    def table(rows, widths=None, head=True):
        t = Table([[Paragraph(str(c), B) for c in r] for r in rows], colWidths=widths, repeatRows=1 if head else 0)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               *([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf5"))] if head else [])]))
        return t

    st += [Paragraph("Criminal Network Analysis — Case Report", H1),
           Paragraph(f"Generated {datetime.now():%Y-%m-%d %H:%M} · synthetic data · {len(A.firs)} FIRs, {len(A.cdr)} calls, {len(A.tx)} transactions · "
                     f"period {A.t_min:%Y-%m-%d} to {A.t_max:%Y-%m-%d}", small), Spacer(1, 6)]

    if eid:
        e = A.entities[eid]; m = M["metrics"].get(eid, {}); r = R[eid]
        st += [Paragraph(f"Subject: {e['name']}", H2),
               table([["Aliases", ", ".join(e["aliases"]) or "-"], ["Role", e["role"]], ["Phones", ", ".join(e["phones"]) or "-"],
                      ["Accounts", ", ".join(e["accounts"]) or "-"], ["Organisation", ", ".join(e["orgs"]) or "-"], ["Vehicles", ", ".join(e["plates"]) or "-"],
                      ["FIRs", ", ".join(e["firs"]) or "-"], ["Group", m.get("community", "-")],
                      ["Risk score", f"{r['score']}/100 ({r['level']}) — network importance {r['breakdown']['centrality']}/40, alerts {r['breakdown']['alert_involvement']}, money moved {r['breakdown']['money_volume']}/20"]],
                     [35 * mm, 140 * mm], head=False), Spacer(1, 6)]
        mine = [a for a in alerts if eid in a["entities"]]
        st.append(Paragraph("Alerts involving subject", H2))
        st.append(table([["ID", "Sev.", "Finding", "Evidence"]] + [[a["id"], a["severity"], a["summary"], ", ".join(a["evidence"]["firs"] + a["evidence"]["txns"][:6] + a["evidence"]["calls"][:4])] for a in mine] if mine else [["No alerts"]],
                        [16 * mm, 14 * mm, 100 * mm, 45 * mm] if mine else None))
        st.append(PageBreak())

    st.append(Paragraph("Key persons (top 5 by importance in the network)", H2))
    rows = [["#", "Name", "Score", "Group", "Why (computed)"]]
    for i, t in enumerate(M["top5"], 1):
        rows.append([i, t["name"], t["score"], t["community"], "<br/>".join(t["reasons"][:4])])
    st += [table(rows, [8 * mm, 32 * mm, 14 * mm, 14 * mm, 108 * mm]), Spacer(1, 8)]

    st.append(Paragraph("Detected groups (people who mostly interact with each other)", H2))
    st.append(table([["Group", "Size", "Lead", "Members"]] + [[c["id"], c["size"], A.name(c["lead"]), ", ".join(A.name(x) for x in c["members"])] for c in M["communities"]],
                    [14 * mm, 12 * mm, 35 * mm, 115 * mm]))
    st.append(Spacer(1, 8))

    st.append(Paragraph("Suspicious patterns", H2))
    st.append(table([["ID", "Sev.", "Type", "Finding", "Evidence ids"]] + [
        [a["id"], a["severity"], a["type"], a["summary"], ", ".join(a["evidence"]["firs"] + a["evidence"]["txns"][:6] + a["evidence"]["calls"][:5])] for a in alerts],
        [15 * mm, 12 * mm, 24 * mm, 85 * mm, 40 * mm]))
    st.append(Spacer(1, 8))

    st.append(Paragraph("Entity resolution notes", H2))
    notes = [f"Phone {p} is attributed to {len(v)} different identities ({', '.join(sorted({x['surface'] for x in v}))}) and was NOT used to merge anyone."
             for p, v in A.R.shared_phones.items()]
    notes += [f"Unresolved mention '{u['surface']}' in {u['fir_id']}: could be {', '.join(A.name(c) for c in u['candidates'])}; left unmerged." for u in A.R.unresolved]
    for n in notes or ["None"]:
        st.append(Paragraph("• " + n, B))
    st += [Spacer(1, 10), Paragraph("All figures are computed programmatically from the supplied FIR, CDR and transaction records. The language model only routes questions and phrases answers; it does not generate findings.", small)]
    doc.build(st)
    return buf.getvalue()
