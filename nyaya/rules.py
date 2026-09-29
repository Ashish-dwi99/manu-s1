"""Rule programs: record excerpts whose answer is computed by the court calculator, never written by a model.

Each generator draws dates and facts, renders a record excerpt the way registries and order sheets write them, adds
the calculator's block ("[computed by the court calculator]"), and computes the label from the facts with the
same statute the bank entry cites. Facts are withheld at random so `cannot_tell` is learned as a real answer.
Party names are drawn from every region and community and never touch the label (fairness by construction).
Boundary days that would fall on a Sunday are redrawn, so no label depends on the court calendar.

Only bank entries not flagged `verify` are generated (see README: v0 trains nothing counsel has not confirmed).
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Callable

from nyaya import calculators as C

FIRST = ["Ramesh", "Fatima", "Joseph", "Gurpreet", "Lakshmi", "Arjun", "Ayesha", "Thomas", "Harpreet", "Meenakshi",
         "Suresh", "Zainab", "Anthony", "Kuldeep", "Priya", "Vijay", "Nasreen", "Mary", "Manjit", "Kavitha", "Rahul",
         "Shabnam", "George", "Sukhwinder", "Anitha", "Prakash", "Rukhsana", "Philip", "Baljit", "Revathi", "Dinesh",
         "Tenzin", "Lalthangliana", "Bikash", "Parveen", "Santosh", "Irfan", "Deepa", "Hemant", "Farida"]
LAST = ["Sharma", "Khan", "Fernandes", "Singh", "Iyer", "Patel", "Siddiqui", "Mathew", "Gill", "Reddy", "Yadav",
        "Ansari", "D'Souza", "Sandhu", "Nair", "Das", "Qureshi", "Varghese", "Dhillon", "Pillai", "Mishra", "Bhat",
        "Chatterjee", "Naidu", "Gowda", "Pathan", "Rao", "Mondal", "Bora", "Sangma", "Marak", "Hussain", "Kaur"]
FIRMS = ["Shree Balaji Traders", "Al-Noor Enterprises", "St. Mary's Agencies", "Guru Nanak Motors", "Sri Venkateswara Textiles",
         "Kaveri Agro Industries", "Brahmaputra Logistics", "Malabar Spices Co.", "Narmada Cement Works", "Deccan Hardware Stores"]
MAGISTRATES = ["the Metropolitan Magistrate (NI Act), Saket, New Delhi", "the Judicial Magistrate First Class, Raibag",
               "the Chief Judicial Magistrate, Ernakulam", "the Judicial Magistrate First Class, Nagpur",
               "the Metropolitan Magistrate, Egmore, Chennai", "the Judicial Magistrate, Patna"]
CIVIL = ["the Civil Judge (Senior Division), Pune", "the Additional District Judge, Lucknow", "the Principal Civil Judge, Coimbatore",
         "the Civil Judge (Junior Division), Guwahati", "the District Judge, Jaipur", "the Civil Judge, Patna"]
COMMERCIAL = ["the Commercial Court, Bengaluru", "the District Judge (Commercial Court), Saket, New Delhi", "the Commercial Court, Ahmedabad"]
FAMILY = ["the Principal Judge, Family Court, Hyderabad", "the Judge, Family Court, Bandra, Mumbai", "the Principal Judge, Family Court, Kolkata"]


def person(rng: random.Random) -> str:
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def party(rng: random.Random) -> str:
    return rng.choice(FIRMS) if rng.random() < 0.3 else person(rng)


def dfmt(d: date, rng: random.Random) -> str:
    style = rng.random()
    if style < 0.6:
        return d.strftime("%d.%m.%Y")
    if style < 0.8:
        return d.strftime("%d/%m/%Y")
    suffix = "th" if 11 <= d.day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d.day % 10, "th")
    return f"{d.day}{suffix} {d.strftime('%B %Y')}"


def rand_date(rng: random.Random, start: date = date(2015, 1, 1), end: date = date(2026, 6, 30)) -> date:
    return start + timedelta(days=rng.randrange((end - start).days))


def weekday_ok(d: date) -> bool:
    return d.weekday() != 6


def calc_block(lines: list[str]) -> str:
    return "\n[computed by the court calculator]\n" + "\n".join(f"- {x}" for x in lines)


def around(rng: random.Random, last_day: date, early: int = 60, late: int = 60) -> date:
    """A date near a boundary: often within a few days of it, where the answer is decided."""
    if rng.random() < 0.5:
        return last_day + timedelta(days=rng.randint(-4, 4))
    return last_day + timedelta(days=rng.randint(-early, late))


class Skip(Exception):
    """This draw lands on a calendar edge the rules avoid; draw again."""


# ── generators: each returns (state, label) for its bank entry ───────────────────────────────────────────────

def ni138_validity(rng):
    drawer, payee, amount = party(rng), party(rng), rng.choice([25000, 50000, 125000, 300000, 750000, 1200000])
    cheque = rand_date(rng)
    w = C.ni138_validity(cheque)
    presented = around(rng, w.last_day, 80, 40)
    known = rng.random() > 0.12
    rec = (f"Complaint under Section 138 of the Negotiable Instruments Act, 1881 before {rng.choice(MAGISTRATES)}.\n"
           f"Complainant: {payee}. Accused: {drawer}.\n"
           f"Cheque No. {rng.randint(100000, 999999)} for Rs. {amount:,} dated {dfmt(cheque, rng)} drawn by the accused.\n")
    if known:
        rec += f"The cheque was presented by the complainant's banker on {dfmt(presented, rng)} and returned unpaid with the memo 'Funds Insufficient'.\n"
        n = C.signed_days(presented, w.last_day)
        calc = [f"Cheque validity: three months from {C.fmt(cheque)}; last day {C.fmt(w.last_day)}.",
                f"Presented on {C.fmt(presented)}: " + ("on the last day." if n == 0 else f"{abs(n)} day(s) {'after' if n > 0 else 'before'} the last day.")]
        label = "within_validity" if n <= 0 else "after_validity"
    else:
        rec += "The cheque was returned unpaid with the memo 'Funds Insufficient'. The date of presentation is not stated in the complaint or its annexures.\n"
        calc = [f"Cheque validity: three months from {C.fmt(cheque)}; last day {C.fmt(w.last_day)}.", "Date of presentation: not in the record."]
        label = "cannot_tell"
    return rec + calc_block(calc), label


def ni138_notice(rng):
    memo = rand_date(rng)
    w = C.ni138_notice(memo)
    r = rng.random()
    rec = (f"Complaint under Section 138 NI Act. Complainant {party(rng)} against {party(rng)}.\n"
           f"Return memo dated {dfmt(memo, rng)} received by the complainant on the same day.\n")
    if r < 0.1:
        rec += "No demand notice is annexed and the complaint does not mention one.\n"
        return rec + calc_block([w.render()]), "no_notice"
    if r < 0.2:
        rec += "A legal notice demanding payment was sent to the accused; its date is illegible in the copy filed.\n"
        return rec + calc_block([w.render(), "Date of the demand notice: not in the record."]), "cannot_tell"
    notice = around(rng, w.last_day, 25, 30)
    rec += f"Demand notice issued by registered post on {dfmt(notice, rng)}.\n"
    n = C.signed_days(notice, w.last_day)
    return rec + calc_block([w.render(notice, "issued")]), ("in_time" if n <= 0 else "late")


def ni138_complaint(rng):
    received = rand_date(rng)
    pay = C.ni138_payment(received)
    arises = C.ni138_cause_of_action(pay)
    w = C.ni138_complaint(arises)
    if not weekday_ok(w.last_day):
        raise Skip
    rec = (f"Complaint under Section 138 read with Section 142 NI Act filed before {rng.choice(MAGISTRATES)} by {party(rng)} against {party(rng)}.\n")
    if rng.random() < 0.12:
        rec += "The demand notice was sent; the complaint does not state when the accused received it, and no tracking report is annexed.\n"
        return rec + calc_block(["Date of receipt of notice: not in the record."]), "cannot_tell"
    filed = around(rng, rng.choice([w.last_day, arises]), 20, 45)
    condonation = filed > w.last_day and rng.random() < 0.5
    rec += (f"The accused received the demand notice on {dfmt(received, rng)} (postal tracking report annexed) and made no payment.\n"
            f"Complaint presented on {dfmt(filed, rng)}.\n")
    if condonation:
        rec += "An application for condonation of delay under the proviso to Section 142(1)(b) is filed with the complaint.\n"
    calc = [pay.render(), f"Cause of action arose on {C.fmt(arises)} (the day after the payment period ended).",
            w.render(filed, "complaint presented")]
    if filed < arises:
        label = "premature"
        calc.append(f"The complaint was presented {(arises - filed).days} day(s) before the cause of action arose.")
    elif filed <= w.last_day:
        label = "in_time"
    else:
        label = "late_condonation_sought" if condonation else "late"
    return rec + calc_block(calc), label


def written_statement(rng):
    commercial = rng.random() < 0.5
    service = rand_date(rng)
    first, outer = C.written_statement(service, commercial)
    if not (weekday_ok(first.last_day) and weekday_ok(outer.last_day)):
        raise Skip
    kind = "commercial suit" if commercial else "civil suit"
    rec = f"Order sheet, {rng.choice(COMMERCIAL if commercial else CIVIL)}, {kind} between {party(rng)} (plaintiff) and {party(rng)} (defendant).\n"
    r = rng.random()
    if r < 0.1:
        rec += "Summons issued to the defendant. The service report is not on record.\n"
        return rec + calc_block(["Date of service: not in the record."]), "cannot_tell"
    rec += f"The defendant was served with summons on {dfmt(service, rng)}.\n"
    if r < 0.2:
        rec += "No written statement has been filed as on date.\n"
        return rec + calc_block([first.render(), outer.render()]), "not_filed"
    filed = around(rng, rng.choice([first.last_day, outer.last_day]), 20, 40)
    if filed <= service:
        raise Skip
    if not commercial and first.last_day < filed <= outer.last_day:
        rec += f"On the defendant's application, further time to file the written statement was allowed by order dated {dfmt(first.last_day - timedelta(days=rng.randint(0, 5)), rng)}.\n"
    rec += f"Written statement filed on {dfmt(filed, rng)}.\n"
    calc = [first.render(filed, "written statement filed"), outer.render(filed, "written statement filed")]
    if filed <= first.last_day:
        label = "within_30_days"
    elif commercial:
        label = "commercial_within_120" if filed <= outer.last_day else "commercial_beyond_120"
    else:
        label = "within_extended_period" if filed <= outer.last_day else "beyond_period_ordinary"
    return rec + calc_block(calc), label


def abatement(rng):
    plaintiff, defendant = person(rng), person(rng)
    rec = f"Suit between {plaintiff} (plaintiff) and {defendant} (defendant) pending before {rng.choice(CIVIL)}.\n"
    today = rand_date(rng, date(2019, 1, 1))
    r = rng.random()
    if r < 0.12:
        rec += f"Order sheet up to {dfmt(today, rng)} records no death of any party.\n"
        return rec + calc_block([f"Record examined up to {C.fmt(today)}."]), "no_death"
    who = rng.choice([plaintiff, defendant])
    if r < 0.22:
        rec += f"Counsel reported on {dfmt(today, rng)} that {who} has died; the date of death is not stated and no death certificate is filed.\n"
        return rec + calc_block(["Date of death: not in the record."]), "cannot_tell"
    death = today - timedelta(days=rng.randint(10, 400))
    w = C.substitution(death)
    if not weekday_ok(w.last_day):
        raise Skip
    rec += f"{who} died on {dfmt(death, rng)} (death certificate filed).\n"
    s = rng.random()
    if s < 0.35:
        applied = death + timedelta(days=rng.randint(5, 88))
        if applied > today:
            raise Skip
        rec += f"Application under Order XXII to bring the legal representatives on record was filed on {dfmt(applied, rng)} and allowed.\n"
        calc = [w.render(applied, "application filed")]
        label = "substituted_in_time" if applied <= w.last_day else "abated_no_setting_aside"
    else:
        rec += f"As on {dfmt(today, rng)} no application to bring the legal representatives on record has been filed.\n"
        calc = [w.render(), f"Record examined up to {C.fmt(today)}: {(today - w.last_day).days} day(s) after the last day." if today > w.last_day
                else f"Record examined up to {C.fmt(today)}: the period has not yet run out."]
        if today <= w.last_day:
            label = "substitution_pending_in_time"
        elif rng.random() < 0.4:
            rec += "An application to set aside the abatement, with an application for condonation of delay, is pending.\n"
            label = "setting_aside_sought"
        else:
            label = "abated_no_setting_aside"
    return rec + calc_block(calc), label


def caveat(rng):
    caveator, applicant = party(rng), party(rng)
    lodged = rand_date(rng)
    w = C.caveat(lodged)
    rec = f"Fresh filing: petition by {applicant} against {caveator} before {rng.choice(CIVIL + COMMERCIAL)}.\n"
    r = rng.random()
    if r < 0.15:
        rec += "The caveat register shows no caveat lodged by any respondent to this petition.\n"
        return rec + calc_block([]), "no_caveat"
    if r < 0.25:
        rec += f"The caveat register shows a caveat lodged by a person named '{rng.choice(FIRST)}' whose address and matter details cannot be matched with this petition.\n"
        return rec + calc_block([]), "cannot_tell"
    filed = around(rng, w.last_day, 60, 60)
    if filed < lodged:
        raise Skip
    rec += f"Caveat under Section 148A CPC lodged by {caveator} on {dfmt(lodged, rng)} in respect of the same order. This petition was filed on {dfmt(filed, rng)}.\n"
    n = C.signed_days(filed, w.last_day)
    return rec + calc_block([w.render(filed, "petition filed")]), ("caveat_subsisting" if n <= 0 else "caveat_lapsed")


def section_80(rng):
    plaintiff = party(rng)
    govt = rng.random() < 0.8
    defendant = rng.choice(["State of Maharashtra through its Secretary, Revenue Department", "Union of India through the General Manager, Northern Railway",
                            "State of Tamil Nadu through the District Collector, Madurai", "The Executive Engineer, Public Works Department, Bhopal"]) if govt else party(rng)
    rec = f"Plaint in a civil suit by {plaintiff} against {defendant}.\n"
    filed = rand_date(rng)
    if not govt:
        rec += f"Suit instituted on {dfmt(filed, rng)}.\n"
        return rec + calc_block([]), "not_applicable"
    r = rng.random()
    if r < 0.12:
        rec += f"Suit instituted on {dfmt(filed, rng)}. The plaint does not mention any notice to the defendant under Section 80 CPC.\n"
        return rec + calc_block([]), "no_notice"
    if r < 0.24:
        rec += (f"Suit instituted on {dfmt(filed, rng)} with an application under Section 80(2) CPC for leave to sue without notice, "
                "pleading that urgent relief against demolition is required.\n")
        return rec + calc_block([]), "leave_sought_urgent"
    if r < 0.32:
        rec += f"Suit instituted on {dfmt(filed, rng)}. The plaint says notice under Section 80 was sent but gives no date and annexes no copy.\n"
        return rec + calc_block(["Date of delivery of notice: not in the record."]), "cannot_tell"
    served = filed - timedelta(days=rng.randint(20, 100))
    w = C.section_80(served)
    rec += f"Notice under Section 80 CPC was delivered to the defendant on {dfmt(served, rng)}. Suit instituted on {dfmt(filed, rng)}.\n"
    n = C.signed_days(filed, w.last_day)
    return rec + calc_block([w.render(filed, "suit instituted")]), ("notice_served_and_period_expired" if n > 0 else "notice_served_period_not_expired")


def arbitration_34(rng):
    received = rand_date(rng)
    first, outer = C.arbitration_34(received)
    if not (weekday_ok(first.last_day) and weekday_ok(outer.last_day)):
        raise Skip
    rec = f"Petition under Section 34 of the Arbitration and Conciliation Act, 1996 by {party(rng)} against {party(rng)} to set aside the award.\n"
    if rng.random() < 0.12:
        rec += "The award is annexed; the petition does not state when the signed copy of the award was received.\n"
        return rec + calc_block(["Date of receipt of the award: not in the record."]), "cannot_tell"
    filed = around(rng, rng.choice([first.last_day, outer.last_day]), 30, 40)
    rec += f"A signed copy of the award was received by the petitioner on {dfmt(received, rng)}. The petition was filed on {dfmt(filed, rng)}.\n"
    calc = [first.render(filed, "petition filed"), outer.render(filed, "petition filed")]
    label = "within_three_months" if filed <= first.last_day else ("within_grace_thirty_days" if filed <= outer.last_day else "beyond_outer_limit")
    return rec + calc_block(calc), label


def consumer_limitation(rng):
    cause = rand_date(rng, date(2020, 7, 20))
    w = C.consumer_complaint(cause)
    if not weekday_ok(w.last_day):
        raise Skip
    rec = f"Consumer complaint by {person(rng)} against {rng.choice(FIRMS)} under the Consumer Protection Act, 2019.\n"
    if rng.random() < 0.12:
        rec += "The complaint alleges deficiency in service in the repair of a vehicle; it does not say when the defect or the refusal occurred.\n"
        return rec + calc_block(["Date of the cause of action: not in the record."]), "cannot_tell"
    filed = around(rng, w.last_day, 90, 120)
    condone = filed > w.last_day and rng.random() < 0.5
    rec += f"The cause of action arose on {dfmt(cause, rng)} when the opposite party refused the refund. Complaint filed on {dfmt(filed, rng)}.\n"
    if condone:
        rec += "An application for condonation of delay is filed with the complaint.\n"
    label = "in_time" if filed <= w.last_day else ("delayed_condonation_sought" if condone else "delayed_no_condonation")
    return rec + calc_block([w.render(filed, "complaint filed")]), label


def mutual_consent(rng):
    first = rand_date(rng)
    w = C.mutual_consent(first)
    rec = f"Petition under Section 13B of the Hindu Marriage Act, 1955 by {person(rng)} and {person(rng)} before {rng.choice(FAMILY)}.\n"
    if rng.random() < 0.12:
        rec += "The second motion is moved today. The order sheet recording the first motion is not in the file.\n"
        return rec + calc_block(["Date of the first motion: not in the record."]), "cannot_tell"
    second = around(rng, w.last_day, 120, 60)
    if second <= first:
        raise Skip
    rec += f"The first motion was recorded on {dfmt(first, rng)}. The second motion is moved on {dfmt(second, rng)}.\n"
    early = second <= w.last_day
    waiver = early and rng.random() < 0.5
    if waiver:
        rec += "An application to waive the remaining waiting period is filed by both parties.\n"
    label = "period_complete" if not early else ("waiver_sought" if waiver else "period_not_complete")
    return rec + calc_block([w.render(second, "second motion moved")]), label


def execution(rng):
    rec = f"Execution petition by {party(rng)} (decree holder) against {party(rng)} (judgment debtor).\n"
    r = rng.random()
    filed = rand_date(rng, date(2010, 1, 1))
    if r < 0.1:
        rec += f"The decree is one for perpetual injunction restraining the judgment debtor from interfering with the decree holder's possession. Execution petition filed on {dfmt(filed, rng)}.\n"
        return rec + calc_block([]), "injunction_no_limit"
    if r < 0.2:
        rec += f"Execution petition filed on {dfmt(filed, rng)} for recovery of money. The copy of the decree filed is illegible as to its date.\n"
        return rec + calc_block(["Date of the decree: not in the record."]), "cannot_tell"
    enforceable = filed - timedelta(days=rng.randint(3000, 5200))
    w = C.execution(enforceable)
    if not weekday_ok(w.last_day):
        raise Skip
    rec += f"Money decree dated {dfmt(enforceable, rng)}, enforceable from that date. Execution petition filed on {dfmt(filed, rng)}.\n"
    return rec + calc_block([w.render(filed, "execution petition filed")]), ("in_time" if filed <= w.last_day else "time_barred")


def code_applicable(rng):
    accused, complainant = person(rng), person(rng)
    r = rng.random()
    base = C.BNS_COMMENCEMENT + timedelta(days=rng.randint(-500, 500))
    rec = f"FIR registered on the complaint of {complainant} against {accused} alleging cheating and criminal breach of trust.\n"
    if r < 0.12:
        rec += "The FIR states that the amounts were misappropriated 'over a period' without giving any dates.\n"
        return rec + calc_block(["Date of the offence: not in the record."]), "cannot_tell"
    if r < 0.25:
        start = C.BNS_COMMENCEMENT - timedelta(days=rng.randint(20, 300))
        end = C.BNS_COMMENCEMENT + timedelta(days=rng.randint(5, 200))
        rec += f"The alleged transactions took place from {dfmt(start, rng)} to {dfmt(end, rng)}.\n"
        return rec + calc_block([f"The BNS 2023 came into force on {C.fmt(C.BNS_COMMENCEMENT)}; the conduct alleged runs from {C.fmt(start)} to {C.fmt(end)}."]), "continuing_across_dates"
    rec += f"The alleged offence was committed on {dfmt(base, rng)}.\n"
    code = C.code_by_offence_date(base)
    return rec + calc_block([f"The BNS 2023 came into force on {C.fmt(C.BNS_COMMENCEMENT)}; the offence date {C.fmt(base)} is "
                             f"{'on or after' if code == 'BNS 2023' else 'before'} it."]), ("bns" if code == "BNS 2023" else "ipc")


def suit_limitation(rng):
    reliefs = [("recovery of the price of goods sold and delivered", 3, "art. 14"), ("compensation for breach of a contract", 3, "art. 55"),
               ("a declaration of title", 3, "art. 58"), ("recovery of money lent", 3, "art. 19"),
               ("possession of immovable property based on title", 12, "art. 65")]
    relief, years, article = rng.choice(reliefs)
    rec = f"Plaint by {party(rng)} against {party(rng)} for {relief}.\n"
    if rng.random() < 0.12:
        rec += "The plaint narrates the transactions but does not state when the cause of action arose.\n"
        return rec + calc_block([f"Period recorded by the registry for this relief: {years} years ({article}).", "Date of the cause of action: not in the record."]), "cannot_tell"
    cause = rand_date(rng, date(2005, 1, 1), date(2023, 1, 1))
    w = C.suit_limitation(cause, years, article)
    if not weekday_ok(w.last_day):
        raise Skip
    filed = around(rng, w.last_day, 200, 300)
    rec += f"The cause of action arose on {dfmt(cause, rng)}. The suit was instituted on {dfmt(filed, rng)}.\n"
    calc = [f"Period recorded by the registry for this relief: {years} years ({article}).", w.render(filed, "suit instituted")]
    if filed <= w.last_day:
        return rec + calc_block(calc), "in_time"
    if rng.random() < 0.5:
        ack = cause + timedelta(days=rng.randint(200, 900))
        rec += f"The plaint pleads a written acknowledgment of liability signed by the defendant on {dfmt(ack, rng)} (Section 18 of the Limitation Act).\n"
        return rec + calc_block(calc), "exclusion_claimed"
    return rec + calc_block(calc), "time_barred"


def adjournments(rng):
    petitioner, respondent = party(rng), party(rng)
    side = rng.choice(["petitioner", "respondent"])
    d = rand_date(rng, date(2016, 1, 1), date(2025, 1, 1))
    lines, count = [], 0
    for _ in range(rng.randint(3, 9)):
        d += timedelta(days=rng.randint(20, 75))
        kind = rng.random()
        if kind < 0.35:
            who = rng.choice(["petitioner", "respondent"])
            count += who == side
            lines.append(f"{dfmt(d, rng)}: Adjournment sought by counsel for the {who}. Allowed. List on the next date.")
        elif kind < 0.55:
            lines.append(f"{dfmt(d, rng)}: Presiding officer on leave. Adjourned.")
        elif kind < 0.75:
            lines.append(f"{dfmt(d, rng)}: Evidence of PW-{rng.randint(1, 6)} recorded in part. Adjourned for further evidence.")
        else:
            lines.append(f"{dfmt(d, rng)}: Arguments on the pending application heard in part.")
    incomplete = rng.random() < 0.1
    rec = f"Order sheet in the matter of {petitioner} (petitioner) v. {respondent} (respondent).\n" + "\n".join(lines) + "\n"
    if incomplete:
        rec += "[Pages of the order sheet between these dates are missing from the file.]\n"
    q_party = f"the {side}"
    label = "cannot_tell" if incomplete else ("none" if count == 0 else "within_limit" if count <= 3 else "beyond_limit")
    return rec + f"\nParty asked about: {q_party}.", label


SPECIAL = {
    # label: (section templates, statute spellings as they appear in real headers)
    "prevention_of_corruption": (["13(2) r/w 13(1)(d)", "7", "7A", "8", "13(1)(b) r/w 13(2)", "12", "13(1)(e)"],
                                 ["PC Act, 1988", "P.C. Act", "Prevention of Corruption Act, 1988", "POC Act", "PC Act"]),
    "ndps": (["8/20", "8(c) r/w 21(c)", "22(c)", "29", "8/18", "27A"],
             ["NDPS Act", "N.D.P.S. Act, 1985", "Narcotic Drugs and Psychotropic Substances Act, 1985", "NDPS"]),
    "pocso": (["4", "6", "8", "10", "12"],
              ["POCSO Act", "P.O.C.S.O. Act, 2012", "Protection of Children from Sexual Offences Act, 2012", "POCSO"]),
    "sc_st_act": (["3(1)(r)", "3(1)(s)", "3(2)(v)", "3(1)(w)(i)"],
                  ["SC/ST (PoA) Act", "SC/ST Act", "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act, 1989", "SC & ST (POA) Act"]),
    "pmla": (["3 r/w 4", "3", "4"], ["PMLA", "PML Act, 2002", "Prevention of Money-laundering Act, 2002"]),
    "uapa_or_nia": (["13", "16", "18", "20", "38", "39"], ["UA(P) Act", "UAPA", "Unlawful Activities (Prevention) Act, 1967"]),
}
ORDINARY = [("302/34", "IPC"), ("420/120-B", "IPC"), ("379", "IPC"), ("498A/406", "IPC"), ("307", "IPC"), ("103(1)", "BNS"),
            ("318(4)", "BNS"), ("303(2)", "BNS"), ("138", "NI Act"), ("25/27", "Arms Act"), ("279/304A", "IPC"), ("64", "BNS")]
HEADER_FORMS = ["{court}\n{case_no}\n{title}\nU/s {sections}.", "FIR No. {fir}, P.S. {ps}\nUnder Sections {sections}\n{title}",
                "{title}\nOffences: {sections}\nCase No. {case_no}", "Charge-sheet filed in FIR No. {fir}, P.S. {ps}, under {sections}. Accused: {accused}."]


def special_court(rng):
    court = rng.choice(["IN THE COURT OF THE SESSIONS JUDGE, " + rng.choice(["NAGPUR", "THANE", "KOTTAYAM", "RANCHI", "MEERUT"]),
                        "IN THE COURT OF THE CHIEF JUDICIAL MAGISTRATE, " + rng.choice(["ALIPORE", "SHIMLA", "BHOPAL"]),
                        "IN THE COURT OF THE ADDITIONAL SESSIONS JUDGE-0" + str(rng.randint(1, 9)) + ", " + rng.choice(["DWARKA", "SAKET", "ROHINI"])])
    fir, ps = f"{rng.randint(12, 980)}/{rng.randint(2016, 2026)}", rng.choice(["Kotwali", "Civil Lines", "Sadar Bazar", "Vasant Kunj", "Adarsh Nagar"])
    accused = person(rng)
    r = rng.random()
    label = "cannot_tell" if r < 0.12 else "none" if r < 0.42 else rng.choice(list(SPECIAL))
    # one penal code per case: the old code or the new one, never both
    code = rng.choice(["IPC", "BNS"])
    ordinary = [(sec, act) for sec, act in ORDINARY if act in (code, "NI Act", "Arms Act")]
    parts = [f"{sec} {act}" for sec, act in rng.sample(ordinary, rng.randint(1, 2))]
    prefix = {"ndps": "NDPS Case", "pocso": "POCSO Case", "prevention_of_corruption": "CC (PC Act)", "pmla": "PMLA Case"}
    neutral = ["SC", "CC", "Sessions Case", "Crl. Case"]
    case_kind = prefix[label] if label in prefix and rng.random() < 0.4 else rng.choice(neutral)
    case_no = f"{case_kind} No. {rng.randint(1, 900)}/{rng.randint(2016, 2026)}"
    prosecutor = {"prevention_of_corruption": ["CBI", "State through Anti-Corruption Bureau"], "pmla": ["Directorate of Enforcement"],
                  "ndps": ["NCB", "State"]}.get(label, ["State"])
    title = f"{rng.choice(prosecutor)} v. {accused}" + (" & Ors." if rng.random() < 0.4 else "")
    if label == "cannot_tell":
        sections = "[sections not legible in the copy filed]"
    else:
        if label != "none":
            secs, spellings = SPECIAL[label]
            parts.insert(rng.randrange(len(parts) + 1), f"Sec. {rng.choice(secs)} of {rng.choice(spellings)}")
        sections = " and ".join(parts) if rng.random() < 0.5 else ", ".join(parts)
    text = rng.choice(HEADER_FORMS).format(court=court, case_no=case_no, title=title, fir=fir, ps=ps, accused=accused, sections=sections)
    return text, label

def appearance(rng):
    """A trial court's "Present:" block. Each accused is present in person (or by video), exempted, or absent; counsel
    entries name the accused they appear for, wrapped across lines as orders write them. The label follows from how
    the block was built."""
    n = rng.randint(2, 6)
    names = {f"A-{i}": (rng.choice(FIRMS) if i == 1 and rng.random() < 0.3 else person(rng)) for i in range(1, n + 1)}
    status = {t: rng.choices(["in_person", "vc", "exempted", "absent"], [0.45, 0.15, 0.25, 0.15])[0] for t in names}
    tags = list(names)
    rng.shuffle(tags)
    counsel_for, groups = set(), []
    while tags and rng.random() < 0.85:
        g = tags[:rng.randint(1, 2)]
        tags = tags[len(g):]
        if rng.random() < 0.8:
            groups.append(g)
            counsel_for |= set(g)
    lines = [f"Present: Ld. {rng.choice(['Sr. PP', 'PP', 'APP'])} Sh. {person(rng)} for the {rng.choice(['State', 'CBI', 'prosecution'])}."]
    for t, nm in names.items():
        st = status[t]
        if st == "in_person":
            lines.append(f"{t} {nm} in person.")
        elif st == "vc":
            lines.append(f"{t} {nm} (through VC).")
        elif st == "exempted":
            lines.append(f"{t} {nm} is absent; application seeking exemption from personal appearance for today moved. Allowed.")
        else:
            lines.append(f"{t} {nm} is absent.")
    for g in groups:
        who = " and ".join(f"{t} {names[t]}" if rng.random() < 0.6 else t for t in g)
        adv = f"Sh. {person(rng)}" + (f" and Sh. {person(rng)}" if rng.random() < 0.4 else "")
        entry = f"Ld. Counsel{'s' if ' and ' in adv else ''} {adv} for {who}."
        spaces = [i for i, ch in enumerate(entry) if ch == " " and 15 < i < len(entry) - 5]
        if rng.random() < 0.5 and spaces:   # wrap between words, as typed orders do
            cut = rng.choice(spaces)
            entry = entry[:cut] + "\n" + entry[cut + 1:]
        lines.append(entry)
    ask = rng.choice(list(names))
    if rng.random() < 0.1:
        ask_name = person(rng)
        return "\n".join(lines) + f"\n\nParty asked about: an accused named {ask_name}.", "cannot_tell"
    st, rep = status[ask], ask in counsel_for
    if st in ("in_person", "vc"):
        label = "in_person_with_counsel" if rep else "in_person_without_counsel"
    elif rep:
        label = "through_counsel_only"
    else:
        label = "cannot_tell"   # absent and unrepresented: whether they were served is not on this page
    return "\n".join(lines) + f"\n\nParty asked about: {ask} {names[ask]}.", label


GENERATORS: dict[str, Callable] = {
    "FCR.NI.01": ni138_validity, "FCR.NI.02": ni138_notice, "FCR.NI.03": ni138_complaint,
    "PLD.WS.01": written_statement, "PND.ABT.01": abatement, "FIL.CAV.01": caveat, "FIL.GOV.01": section_80,
    "SPL.ARB.01": arbitration_34, "SPL.CON.02": consumer_limitation, "SPL.MAT.01": mutual_consent,
    "EXE.LIM.01": execution, "CRM.CODE.01": code_applicable, "FIL.LIM.01": suit_limitation, "HRG.ADJ.01": adjournments,
    "REG.SPL.01": special_court, "SRV.APR.01": appearance,
}


def generate(bank_id: str, n: int, seed: int) -> list[tuple[str, str]]:
    rng, fn, out = random.Random(f"{bank_id}:{seed}"), GENERATORS[bank_id], []
    while len(out) < n:
        try:
            out.append(fn(rng))
        except Skip:
            continue
    return out
