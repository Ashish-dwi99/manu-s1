from datetime import date

from nyaya import calculators as C


def test_months_clamp_to_month_end():
    assert C.add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert C.add_months(date(2023, 1, 31), 1) == date(2023, 2, 28)
    assert C.add_months(date(2023, 11, 30), 3) == date(2024, 2, 29)


def test_starting_day_excluded_for_days():
    # thirty days from 1 March: the 1st is excluded, the 31st is the last day
    assert C.add_period(date(2024, 3, 1), days=30) == date(2024, 3, 31)


def test_sunday_extends_to_monday():
    w = C.window("x", date(2024, 3, 1), days=30)   # 31.03.2024 is a Sunday
    assert w.last_day == date(2024, 3, 31) and w.effective_last_day == date(2024, 4, 1)


def test_holiday_calendar_extends():
    w = C.window("x", date(2024, 3, 2), days=30, closed=[date(2024, 4, 1)])   # 01.04 a holiday, 31.03 not the last day
    assert w.last_day == date(2024, 4, 1) and w.effective_last_day == date(2024, 4, 2)


def test_ni138_chain():
    notice = C.ni138_payment(date(2023, 2, 10))              # drawer received notice on 10.02
    assert notice.last_day == date(2023, 2, 25)              # fifteen days to pay
    arises = C.ni138_cause_of_action(notice)                 # not paid by 25.02, so it arises on 26.02
    assert arises == date(2023, 2, 26)
    complaint = C.ni138_complaint(arises)                    # one calendar month, 26.02 excluded
    assert complaint.last_day == date(2023, 3, 26)


def test_written_statement_commercial_outer_limit():
    first, outer = C.written_statement(date(2024, 1, 10), commercial=True)
    assert first.last_day == date(2024, 2, 9) and outer.last_day == date(2024, 5, 9)


def test_arbitration_outer_limit_chain():
    first, outer = C.arbitration_34(date(2024, 1, 15))
    assert first.last_day == date(2024, 4, 15) and outer.last_day == date(2024, 5, 15)


def test_render_reports_signed_days():
    w = C.window("Period", date(2024, 1, 1), days=10)
    assert "1 day(s) after the last day" in w.render(date(2024, 1, 12))
    assert "on the last day" in w.render(date(2024, 1, 11))


def test_code_by_offence_date():
    assert C.code_by_offence_date(date(2024, 6, 30)) == "IPC 1860"
    assert C.code_by_offence_date(date(2024, 7, 1)) == "BNS 2023"
