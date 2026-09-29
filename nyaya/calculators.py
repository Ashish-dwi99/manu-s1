"""The court calculator: exact legal date arithmetic, done by code and handed to the model as facts.

The model never adds days or compares dates itself (that is where decision models fail: JevBench's date family is
20% for Kev-4B). The calculator computes periods, due dates and signed day counts; the model reads them together
with the record and decides which answer the record supports, including "the record does not say".

Conventions (Limitation Act 1963 and General Clauses Act 1897):
  - The day from which a period runs is excluded (Limitation Act s.12(1); General Clauses Act s.9).
  - A month is a British calendar month (General Clauses Act s.3(35)); adding months keeps the day of month,
    clamped to the month's last day.
  - When a period expires on a day the court is closed, the filing may be made on the day it reopens
    (Limitation Act s.4). The court calendar is passed in; without one, only Sundays count as closed.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def add_period(start: date, days: int = 0, months: int = 0, years: int = 0) -> date:
    """The last day of a period that runs from `start` (the starting day itself excluded)."""
    end = add_months(start, months + 12 * years)
    return end + timedelta(days=days)


def next_open_day(d: date, closed: Iterable[date] = ()) -> date:
    closed = set(closed)
    while d.weekday() == 6 or d in closed:
        d += timedelta(days=1)
    return d


def signed_days(filed: date, last_day: date) -> int:
    """Days after (+) or before (-) the last day: 0 means filed on the last day."""
    return (filed - last_day).days


def fmt(d: date) -> str:
    return d.strftime("%d.%m.%Y")


@dataclass(frozen=True)
class Window:
    """A period's computed facts, rendered for the model."""
    name: str
    runs_from: date
    last_day: date
    effective_last_day: date   # after s.4 (court closed on the last day)
    excluded_days: int = 0

    def render(self, filed: date | None = None, what: str = "filed") -> str:
        parts = [f"{self.name}: runs from {fmt(self.runs_from)}"]
        if self.excluded_days:
            parts.append(f"{self.excluded_days} day(s) excluded")
        parts.append(f"last day {fmt(self.last_day)}")
        if self.effective_last_day != self.last_day:
            parts.append(f"court closed that day, so it extends to {fmt(self.effective_last_day)}")
        line = "; ".join(parts) + "."
        if filed is not None:
            n = signed_days(filed, self.effective_last_day)
            rel = ("on the last day" if n == 0 else f"{abs(n)} day(s) {'after' if n > 0 else 'before'} the last day")
            line += f" {what.capitalize()} on {fmt(filed)}: {rel}."
        return line


def window(name: str, runs_from: date, *, days: int = 0, months: int = 0, years: int = 0,
           excluded_days: int = 0, closed: Iterable[date] = (), court_filing: bool = True) -> Window:
    """`court_filing`: a deadline for presenting something in court, which s.4 extends past a closed day. Periods
    that are not court filings (a cheque's validity, a notice period, a waiting period) are never extended."""
    last = add_period(runs_from, days=days + excluded_days, months=months, years=years)
    return Window(name, runs_from, last, next_open_day(last, closed) if court_filing else last, excluded_days)


# ── statutory windows used by the rule programs (each cites its source; see bank/ for the decisions) ────────────

def ni138_validity(cheque_date: date) -> Window:
    """A cheque is payable for three months from its date (RBI directions; s.138 proviso (a))."""
    return window("Cheque validity (three months from its date)", cheque_date, months=3, court_filing=False)


def ni138_notice(return_memo_received: date) -> Window:
    """Demand notice within thirty days of receiving information of dishonour (s.138 proviso (b))."""
    return window("Demand notice period (thirty days from information of dishonour)", return_memo_received, days=30, court_filing=False)


def ni138_payment(notice_received: date) -> Window:
    """The drawer has fifteen days from receipt of notice to pay (s.138 proviso (c))."""
    return window("Payment period (fifteen days from receipt of notice)", notice_received, days=15, court_filing=False)


def ni138_cause_of_action(payment: Window) -> date:
    """The cause of action arises when the drawer fails to pay within the fifteen days: the day after the payment
    period ends (s.138(c)). A complaint filed before this day is premature."""
    return payment.last_day + timedelta(days=1)


def ni138_complaint(cause_of_action: date) -> Window:
    """Complaint within one month of the date the cause of action arises (s.142(1)(b)); that day is excluded and a
    month is a calendar month (Econ Antri Ltd v Rom Industries Ltd, (2014) 11 SCC 769)."""
    return window("Complaint period (one month from the day the cause of action arose)", cause_of_action, months=1)


def written_statement(service: date, commercial: bool) -> list[Window]:
    """CPC Order VIII rule 1: thirty days from service; ordinary suits extendable to ninety; commercial suits to
    one hundred and twenty, after which the right is forfeited."""
    first = window("Written statement period (thirty days from service)", service, days=30)
    outer = (window("Outer limit for a commercial suit (one hundred and twenty days from service)", service, days=120)
             if commercial else window("Extended period for an ordinary suit (ninety days from service)", service, days=90))
    return [first, outer]


def substitution(death: date) -> Window:
    """Limitation Act Schedule art. 120: ninety days from death to bring legal representatives on record."""
    return window("Substitution period (ninety days from the date of death)", death, days=90)


def caveat(lodged: date) -> Window:
    """CPC s.148A(5): a caveat remains in force for ninety days from lodging."""
    return window("Caveat in force (ninety days from lodging)", lodged, days=90, court_filing=False)


def section_80(notice_served: date) -> Window:
    """CPC s.80(1): no suit until two months after notice is delivered."""
    return window("Notice period (two months from delivery of notice)", notice_served, months=2, court_filing=False)


def arbitration_34(award_received: date) -> list[Window]:
    """Arbitration and Conciliation Act s.34(3): three months from receipt, plus up to thirty days on cause shown."""
    first = window("Challenge period (three months from receipt of the award)", award_received, months=3)
    return [first, window("Outer limit (a further thirty days)", first.last_day, days=30)]


def consumer_complaint(cause_of_action: date) -> Window:
    """Consumer Protection Act 2019 s.69(1): two years from the cause of action."""
    return window("Complaint period (two years from the cause of action)", cause_of_action, years=2)


def mutual_consent(first_motion: date) -> Window:
    """Hindu Marriage Act s.13B(2): the second motion is not before six months from the first."""
    return window("Waiting period (six months from the first motion)", first_motion, months=6, court_filing=False)


def execution(decree_enforceable: date) -> Window:
    """Limitation Act Schedule art. 136: twelve years from when the decree becomes enforceable."""
    return window("Execution period (twelve years from enforceability)", decree_enforceable, years=12)


def suit_limitation(cause_of_action: date, years: int, article: str, excluded_days: int = 0) -> Window:
    return window(f"Limitation for the suit ({years} years, {article})", cause_of_action, years=years, excluded_days=excluded_days)


BNS_COMMENCEMENT = date(2024, 7, 1)   # BNS, BNSS and BSA in force (notification of 2024)


def code_by_offence_date(offence: date) -> str:
    return "BNS 2023" if offence >= BNS_COMMENCEMENT else "IPC 1860"
