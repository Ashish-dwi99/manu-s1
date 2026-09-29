"""Turn the live run (data/demo/results.json) into the demo page (demo/nyaya_case_desk.html).

  python3 demo/build_page.py

Everything shown comes from the run: answers, confidences and per-decision milliseconds. The page computes no
answer of its own. A High Court record is flagged only when the model is at least FLAG_CONF sure and its outcome
differs from the court database's; the featured order is chosen by rule (most accused named), not by hand.
"""
import json
import os
import re
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FLAG_CONF = 0.8
QUESTION = {"validity": "Cheque presented in time?", "notice": "Notice sent in time?", "complaint": "Complaint filed in time?"}
LINE = {"On time": "All three deadlines met", "Filed too early": "Filed before the payment period ended: premature",
        "Late, with a condonation application": "Filed after the month ran out, with an application to condone the delay",
        "The record is silent": "No date of receipt of notice: the model says it can't tell"}


def main() -> None:
    run = json.load(open(os.path.join(ROOT, "data", "demo", "results.json")))
    res = run["results"]
    ms_all = sorted(r["ms"] for r in res)

    # 1. the trial file
    orders = []
    by_order = {}
    for r in res:
        if r["group"] == "cbi":
            by_order.setdefault(r["order"], []).append(r)
    accused = {}
    for i, o in enumerate(run["cbi_orders"]):
        rs = by_order.get(o["date"], [])
        kind = next((x for x in rs if x["kind"] == "order_kind"), None)
        nxt = next((x for x in rs if x["kind"] == "next_date"), None)
        appear = {}
        for x in rs:
            if x["kind"] == "appearance":
                appear[x["accused"]] = {"answer": x["answer"], "conf": x["confidence"], "ms": x["ms"], "name": x.get("name", "")}
                if x.get("name") and len(x["name"]) > len(accused.get(x["accused"], "")):
                    accused[x["accused"]] = x["name"]
        orders.append({"index": i, "date": o["date"], "next_fixed": o.get("next_fixed"), "witnesses": o.get("witnesses_mentioned", []),
                       "excerpt": o["text"][:3500],
                       "kind": {"answer": kind["answer"], "conf": kind["confidence"], "ms": kind["ms"]} if kind else {"answer": "cannot_tell", "conf": 0, "ms": 0},
                       "next": ({"answer": nxt["answer"], "conf": nxt["confidence"], "ms": nxt["ms"], "on_file": nxt.get("next_on_file")} if nxt else None),
                       "appear": appear, "decisions": len(rs), "ms": sum(x["ms"] for x in rs)})
    special = next(({"answer": r["answer"], "conf": r["confidence"], "ms": r["ms"]} for r in res if r["kind"] == "special_court"), None)
    featured = max(range(len(orders)), key=lambda i: (len(orders[i]["appear"]), -i))
    # "came in person": the model's answer against the orders that record an accused in person (real-case test set)
    app = {(r["order"], r["accused"]): r["answer"] for r in res if r["group"] == "cbi" and r["kind"] == "appearance"}
    hits = total = 0
    for line in open(os.path.join(ROOT, "data", "final_v1", "test_cbi.jsonl")):
        t = json.loads(line)
        if t["bank_id"] == "SRV.APR.01":
            _, d, _, tag = t["id"].split(":")
            if (d, tag) in app:
                total += 1
                hits += app[(d, tag)].startswith("in_person")
    inperson_check = f"{hits} of {total} times"
    stop = {"who", "is", "are", "in", "and", "has", "have", "through", "submit", "submits", "that", "they", "for", "the", "absent", "present", "was"}
    cand = {}
    for r in res:
        if r["group"] == "cbi" and r["kind"] == "appearance" and r.get("name"):
            words = []
            for w in re.sub(r"\s+", " ", r["name"]).split(" "):
                if w.lower() in stop or not (w[:1].isupper() or w in ("M/s",)):
                    break
                words.append(w.rstrip("-"))
            if words:
                cand.setdefault(r["accused"], []).append(" ".join(words[:4]))
    from collections import Counter
    clean = {t: Counter(v).most_common(1)[0][0] for t, v in cand.items()}
    # a company accused is usually written "A-1 Company"; its name is in the case title
    title = re.search(r"Vs?\.?\s+(M/s\.?\s+[A-Z][A-Za-z\. ]+?(?:Ltd|Limited)\.?)", run["cbi_orders"][0]["text"])
    for t, n in list(clean.items()):
        if n.lower() == "company" and title:
            clean[t] = title.group(1).strip()
    cbi = {"orders": orders, "accused": [{"tag": t, "name": clean.get(t, "")} for t in sorted(accused, key=lambda t: int(t[2:]))],
           "special": special, "featured": featured, "inperson_check": inperson_check, "pages": sum(o.get("pages", 0) for o in run["cbi_orders"])}

    # 2. cheque-bounce samples
    ni, seen = [], {}
    for r in res:
        if r["group"] != "ni138":
            continue
        s = seen.setdefault(r["story"], {"story": r["story"], "line": LINE.get(r["story"], ""), "answers": []})
        s["answers"].append({"question": QUESTION[r["kind"]], "answer": r["answer"], "conf": r["confidence"], "ms": r["ms"], "expected": r["expected"]})
    for d in json.load(open(os.path.join(ROOT, "data", "demo", "inputs.json")))["decisions"]:
        if d["group"] == "ni138" and d["kind"] == "complaint":
            facts = d["state"].split("[computed by the court calculator]")
            seen[d["story"]]["facts"] = facts[0].replace("SAMPLE COMPLAINT (for demonstration)\n", "").strip() + "\n\nCourt calculator:\n" + facts[1].strip()
    ni = list(seen.values())

    # 3. High Court orders
    docs = {}
    for r in res:
        if r["group"] == "hc":
            docs.setdefault(r["key"], {"court": r.get("court"), "case_type": r.get("case_type"), "database": r.get("database_outcome"),
                                       "database_label": r.get("database_label"), "ms": 0})
            docs[r["key"]][r["kind"]] = {"answer": r["answer"], "conf": r["confidence"]}
            docs[r["key"]]["ms"] += r["ms"]
    rows = list(docs.values())
    for d in rows:
        d["flag"] = d["outcome"]["answer"] != d["database_label"] and d["outcome"]["conf"] >= FLAG_CONF
    agree = sum(d["outcome"]["answer"] == d["database_label"] for d in rows) / max(1, len(rows))
    shown = [d for d in rows if d["flag"]][:6] + [d for d in rows if not d["flag"]][:10]
    court_names = {"29_3": "Karnataka HC", "33_10": "Madras HC", "1_12": "J&K HC", "32_4": "Kerala HC", "27_1": "Bombay HC",
                   "19_16": "Calcutta HC", "9_13": "Allahabad HC", "24_17": "Gujarat HC", "28_2": "Andhra Pradesh HC", "36_29": "Telangana HC"}
    for d in shown:
        d["court"] = court_names.get(d["court"], "High Court")
    hc = {"n": len(rows), "ms": sum(d["ms"] for d in rows), "agree": agree, "flagged": sum(d["flag"] for d in rows), "rows": shown}

    data = {"run": {"version": "v1" if "v1" in run["model"] else "v0", "gpu": run["gpu"], "run_at": run["run_at_utc"], "n": len(res),
                    "median_ms": statistics.median(ms_all), "p95_ms": ms_all[int(0.95 * len(ms_all))], "total_s": run["total_s"],
                    "rate": len(res) / max(1e-9, run["total_s"]),
                    "cant": sum(r["answer"] == "cannot_tell" for r in res)},
            "cbi": cbi, "ni": ni, "hc": hc}
    json.dump(data, open(os.path.join(HERE, "page_data.json"), "w"), ensure_ascii=False)
    html = open(os.path.join(HERE, "page_template.html")).read().replace("/*DATA*/null", json.dumps(data, ensure_ascii=False))
    out = os.path.join(HERE, "manu_case_desk.html")
    open(out, "w").write(html)
    print(f"wrote {out} ({len(html) / 1e6:.1f} MB): {len(orders)} orders, {len(ni)} complaints, {len(rows)} HC orders "
          f"({hc['flagged']} flagged, {agree:.0%} agree), median {data['run']['median_ms']:.1f} ms, {data['run']['rate']:.0f}/s")


if __name__ == "__main__":
    main()
