"""A standalone, offline Persian payroll manager for a catering business."""

from __future__ import annotations

import os
import re
import sys
import tkinter as tk
from datetime import date, timedelta
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter import font as tkfont
from unicodedata import decimal

if __package__:
    from .calendar_utils import (
        JALALI_MONTHS,
        format_jalali_date,
        jalali_date_from_gregorian,
        jalali_month_length,
        parse_jalali_date,
        shift_jalali_month,
        gregorian_date_from_jalali,
    )
    from .payroll_store import PayrollError, PayrollStore
else:
    from calendar_utils import (
        JALALI_MONTHS,
        format_jalali_date,
        jalali_date_from_gregorian,
        jalali_month_length,
        parse_jalali_date,
        shift_jalali_month,
        gregorian_date_from_jalali,
    )
    from payroll_store import PayrollError, PayrollStore


APP_NAME = "مدیریت حقوق کترینگ"
GOLD = "#a9823b"
GOLD_DARK = "#806126"
GOLD_PALE = "#f7f1e5"
GOLD_LINE = "#e9dfca"
INK = "#302c25"
MUTED = "#888173"
PAPER = "#faf9f6"
WHITE = "#ffffff"
GREEN = "#4c7d61"
RED = "#a35045"
FONT = "Segoe UI"
FONT_FALLBACKS = ("Segoe UI", "Noto Sans Arabic", "Noto Sans", "DejaVu Sans", "Tahoma", "Arial")
WESTERN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def application_data_directory() -> Path:
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA")
        if root:
            return Path(root) / "CateringPayroll"
    return Path.home() / ".local" / "share" / "catering-payroll"


def local_digits(value: object) -> str:
    return "".join(
        str(decimal(character)) if character.isdecimal() else character
        for character in str(value)
    )


def money(value: int) -> str:
    return f"{value:,} تومان"


def format_grouped_input(value: str) -> str:
    digits = "".join(str(decimal(character)) for character in value if character.isdecimal())
    return re.sub(r"\B(?=(\d{3})+(?!\d))", ",", digits)


def parse_local_integer(value: str) -> int:
    normalized = "".join(
        str(decimal(character)) if character.isdecimal() else character
        for character in value.translate(WESTERN_DIGITS)
    )
    normalized = normalized.replace(",", "").replace("٬", "").replace(" ", "")
    if not normalized.isdecimal():
        raise ValueError("مبلغ باید عدد صحیح باشد.")
    return int(normalized)


def current_month() -> str:
    year, month, _day = jalali_date_from_gregorian(date.today())
    return f"{year:04d}-{month:02d}"


def shift_month(month: str, offset: int) -> str:
    year, number = (int(value) for value in month.split("-"))
    shifted_year, shifted_month = shift_jalali_month(year, number, offset)
    return f"{shifted_year:04d}-{shifted_month:02d}"


def format_month(month: str) -> str:
    year, number = (int(value) for value in month.split("-"))
    return f"{JALALI_MONTHS[number - 1]} {year}"


class PayrollApp:
    def __init__(self, root: tk.Tk, store: PayrollStore) -> None:
        self.root = root
        self.store = store
        self.month = current_month()
        self.employee_filter = tk.StringVar()
        self.root.title(APP_NAME)
        self.root.geometry("1280x820")
        self.root.minsize(960, 680)
        if sys.platform == "win32":
            self.root.state("zoomed")
        self.root.configure(bg=PAPER)
        self._configure_font()
        self.root.option_add("*Font", (FONT, 10))
        self.root.option_add("*TCombobox*Listbox.font", (FONT, 10))
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._style_widgets()
        self._scroll_targets: dict[str, tk.Canvas] = {}
        self._build()
        self.root.bind_all("<MouseWheel>", self._handle_mousewheel, add="+")
        self.root.bind_all("<Button-4>", self._handle_mousewheel, add="+")
        self.root.bind_all("<Button-5>", self._handle_mousewheel, add="+")
        self._accent_progress = 0
        self.root.after(35, self._animate_accent)
        self.refresh()
        self.root.after(350, self._check_payday_reminders)

    def _configure_font(self) -> None:
        global FONT
        available = set(tkfont.families(self.root))
        FONT = next((family for family in FONT_FALLBACKS if family in available), "TkDefaultFont")
        self.root.option_add("*Font", (FONT, 10))

    def _style_widgets(self) -> None:
        style = ttk.Style(self.root)
        available = style.theme_names()
        style.theme_use("clam" if "clam" in available else available[0])
        style.configure(
            "Payroll.TCombobox",
            fieldbackground=WHITE,
            background=WHITE,
            foreground=INK,
            arrowcolor=GOLD_DARK,
            bordercolor=GOLD_LINE,
            lightcolor=GOLD_LINE,
            darkcolor=GOLD_LINE,
            padding=8,
        )
        style.map("Payroll.TCombobox", fieldbackground=[("readonly", WHITE)])

    def _build(self) -> None:
        shell = tk.Frame(self.root, bg=PAPER)
        shell.pack(fill="both", expand=True, padx=32, pady=(22, 18))

        self.accent = tk.Canvas(shell, height=7, bg=PAPER, highlightthickness=0)
        self.accent.pack(fill="x", pady=(0, 17))
        self.accent.create_rectangle(0, 2, 1, 5, fill=GOLD_LINE, outline="", tags="track")
        self.accent_line = self.accent.create_rectangle(0, 2, 1, 5, fill=GOLD, outline="")
        self.accent_shimmer = self.accent.create_rectangle(0, 1, 0, 6, fill="#e8c982", outline="")

        self.header = tk.Frame(shell, bg=PAPER)
        self.header.pack(fill="x", pady=(0, 17))
        heading = tk.Frame(self.header, bg=PAPER)
        heading.pack(side="right", anchor="e")
        tk.Label(
            heading,
            text="دفتر مالی کارکنان",
            bg=PAPER,
            fg=GOLD,
            font=(FONT, 9, "bold"),
            anchor="e",
        ).pack(anchor="e")
        tk.Label(
            heading,
            text="حقوق و دستمزد",
            bg=PAPER,
            fg=INK,
            font=(FONT, 27, "bold"),
            anchor="e",
        ).pack(anchor="e", pady=(4, 2))
        tk.Label(
            heading,
            text="پرداخت‌های مرحله‌ای را ثبت کنید و مانده‌ی حقوق را در یک نگاه ببینید.",
            bg=PAPER,
            fg=MUTED,
            font=(FONT, 9),
            anchor="e",
        ).pack(anchor="e")

        header_actions = tk.Frame(self.header, bg=PAPER)
        header_actions.pack(side="left", anchor="n", pady=(11, 0))
        self.add_button = self._button(
            header_actions, "＋  افزودن کارمند", self.add_employee, primary=True
        )
        self.add_button.pack(side="right", padx=(7, 0))
        self._button(
            header_actions, "◈  هزینه‌ها و گزارش‌ها", self.open_expenses, quiet=True
        ).pack(side="right")

        self.month_bar = tk.Frame(shell, bg=PAPER)
        self.month_bar.pack(fill="x", pady=(0, 12))
        self.month_title = tk.Label(
            self.month_bar,
            text="",
            bg=PAPER,
            fg=INK,
            font=(FONT, 13, "bold"),
            anchor="e",
        )
        self.month_title.pack(side="right", padx=(10, 4))
        self._button(self.month_bar, "›", lambda: self.change_month(1), compact=True).pack(side="right")
        self._button(self.month_bar, "‹", lambda: self.change_month(-1), compact=True).pack(side="right", padx=(5, 0))
        self._button(self.month_bar, "امروز", self.go_to_current_month, quiet=True).pack(side="left")

        self.reminder_frame = tk.Frame(
            shell, bg="#fff8e8", highlightthickness=1, highlightbackground="#edcf8d"
        )
        self.reminder_text = tk.Label(
            self.reminder_frame,
            text="",
            bg="#fff8e8",
            fg=GOLD_DARK,
            font=(FONT, 10, "bold"),
            justify="right",
            anchor="e",
            padx=15,
            pady=11,
            wraplength=1040,
        )
        self.reminder_text.pack(fill="x")

        self.summary_frame = tk.Frame(shell, bg=PAPER)
        self.summary_frame.pack(fill="x", pady=(0, 14))
        self.summary_values: dict[str, tk.Label] = {}
        self._build_summary_card("active_count", "کارکنان فعال", "♙")
        self._build_summary_card("salary", "حقوق این ماه", "◈")
        self._build_summary_card("paid", "پرداخت‌شده", "✓", green=True)
        self._build_summary_card("due", "مانده‌ی حقوق", "◷", due=True)

        list_panel = self._panel(shell)
        list_panel.pack(fill="both", expand=True, pady=(0, 12))
        list_heading = tk.Frame(list_panel, bg=WHITE)
        list_heading.pack(fill="x", padx=16, pady=(14, 11))
        tk.Label(
            list_heading,
            text="وضعیت حقوق ماهانه",
            bg=WHITE,
            fg=INK,
            font=(FONT, 13, "bold"),
            anchor="e",
        ).pack(side="right", anchor="e")
        self.search_entry = self._entry(list_heading, self.employee_filter, "جست‌وجوی نام یا سمت")
        self.search_entry.pack(side="left", ipadx=5, ipady=7)
        self.employee_filter.trace_add("write", lambda *_: self.refresh_employees())

        self.employee_canvas = tk.Canvas(list_panel, bg=WHITE, highlightthickness=0)
        self.employee_scroll = ttk.Scrollbar(
            list_panel, orient="vertical", command=self.employee_canvas.yview
        )
        self.employee_canvas.configure(yscrollcommand=self.employee_scroll.set)
        self.employee_scroll.pack(side="left", fill="y", padx=(0, 4), pady=(0, 8))
        self.employee_canvas.pack(side="right", fill="both", expand=True, padx=(8, 0), pady=(0, 8))
        self.employee_inner = tk.Frame(self.employee_canvas, bg=WHITE)
        self.employee_window = self.employee_canvas.create_window(
            (0, 0), window=self.employee_inner, anchor="nw"
        )
        self.employee_inner.bind("<Configure>", self._resize_employee_scroll)
        self.employee_canvas.bind("<Configure>", self._resize_employee_canvas)
        self._register_scroll_canvas(
            self.employee_canvas, self.employee_inner, self.employee_scroll
        )

        ledger_panel = self._panel(shell)
        ledger_panel.pack(fill="x")
        ledger_heading = tk.Frame(ledger_panel, bg=WHITE)
        ledger_heading.pack(fill="x", padx=16, pady=(13, 5))
        tk.Label(
            ledger_heading,
            text="دفتر پرداخت‌های این ماه",
            bg=WHITE,
            fg=INK,
            font=(FONT, 12, "bold"),
            anchor="e",
        ).pack(side="right")
        self.payment_count = tk.Label(
            ledger_heading, text="", bg=WHITE, fg=MUTED, font=(FONT, 9), anchor="w"
        )
        self.payment_count.pack(side="left")
        self.ledger = tk.Frame(ledger_panel, bg=WHITE)
        self.ledger.pack(fill="x", padx=16, pady=(0, 9))

        footer = tk.Label(
            shell,
            text="●  برنامه‌ی کاملاً آفلاین  ·  اطلاعات فقط روی همین رایانه ذخیره می‌شود",
            bg=PAPER,
            fg="#8a887e",
            font=(FONT, 8),
            anchor="center",
        )
        footer.pack(fill="x", pady=(11, 0))

    def _animate_accent(self) -> None:
        width = self.accent.winfo_width()
        if width <= 1:
            self.root.after(25, self._animate_accent)
            return
        self.accent.coords(self.accent_line, 0, 2, width, 5)
        shimmer_width = min(130, max(40, width // 8))
        position = (self._accent_progress * 13) % (width + shimmer_width) - shimmer_width
        self.accent.coords(self.accent_shimmer, position, 1, position + shimmer_width, 6)
        self._accent_progress += 1
        if self._accent_progress < 92:
            self.root.after(18, self._animate_accent)

    @staticmethod
    def _mix_color(start: str, end: str, progress: float) -> str:
        start_rgb = tuple(int(start[index:index + 2], 16) for index in (1, 3, 5))
        end_rgb = tuple(int(end[index:index + 2], 16) for index in (1, 3, 5))
        mixed = tuple(round(first + (last - first) * progress) for first, last in zip(start_rgb, end_rgb))
        return "#{:02x}{:02x}{:02x}".format(*mixed)

    def _animate_button(
        self, button: tk.Button, *, hovered: bool, primary: bool, danger: bool = False
    ) -> None:
        if str(button.cget("state")) == "disabled":
            return
        start = button.cget("bg")
        if danger:
            target = "#863d35" if hovered else RED
        else:
            target = GOLD_DARK if primary and hovered else GOLD if primary else "#eee6d5" if hovered else "#f6f3ec"
        if start == target:
            return

        def step(frame: int = 1) -> None:
            if not button.winfo_exists():
                return
            button.configure(bg=self._mix_color(start, target, frame / 5))
            if frame < 5:
                button.after(17, lambda: step(frame + 1))

        step()

    @staticmethod
    def _bind_surface_hover(widget: tk.Widget, *, normal: str, hover: str) -> None:
        widget.bind("<Enter>", lambda _event: widget.configure(highlightbackground=hover))
        widget.bind("<Leave>", lambda _event: widget.configure(highlightbackground=normal))

    def _panel(self, parent: tk.Widget) -> tk.Frame:
        return tk.Frame(parent, bg=WHITE, highlightthickness=1, highlightbackground="#eeeae1")

    def _build_summary_card(self, key: str, title: str, icon: str, *, green: bool = False, due: bool = False) -> None:
        self.summary_frame.grid_columnconfigure(len(self.summary_values), weight=1, uniform="summary")
        card = tk.Frame(
            self.summary_frame, bg=WHITE, highlightthickness=1, highlightbackground="#eeeae1"
        )
        card.grid(row=0, column=len(self.summary_values), sticky="nsew", padx=(5, 5))
        self._bind_surface_hover(card, normal="#eeeae1", hover="#d3bd8c")
        accent = GREEN if green else GOLD_DARK if due else GOLD
        icon_bg = "#edf4ef" if green else GOLD_PALE
        tk.Label(
            card,
            text=icon,
            bg=icon_bg,
            fg=accent,
            font=(FONT, 15, "bold"),
            width=3,
            height=1,
        ).pack(side="right", padx=(11, 0), pady=14, anchor="center")
        text_box = tk.Frame(card, bg=WHITE)
        text_box.pack(side="right", fill="both", expand=True, pady=12)
        tk.Label(
            text_box, text=title, bg=WHITE, fg=MUTED, font=(FONT, 8), anchor="e"
        ).pack(anchor="e")
        value = tk.Label(
            text_box,
            text="",
            bg=WHITE,
            fg=GOLD_DARK if due else INK,
            font=(FONT, 11, "bold"),
            anchor="e",
        )
        value.pack(anchor="e", pady=(6, 0))
        self.summary_values[key] = value

    def _button(
        self,
        parent: tk.Widget,
        text: str,
        command,
        *,
        primary: bool = False,
        quiet: bool = False,
        compact: bool = False,
        danger: bool = False,
    ) -> tk.Button:
        background = RED if danger else GOLD if primary else "#f6f3ec" if quiet or compact else WHITE
        foreground = WHITE if primary or danger else GOLD_DARK if quiet or compact else INK
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=background,
            fg=foreground,
            activebackground="#863d35" if danger else GOLD_DARK if primary else GOLD_PALE,
            activeforeground=WHITE if primary or danger else GOLD_DARK,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=(FONT, 9, "bold" if primary else "normal"),
            padx=13 if not compact else 9,
            pady=8 if not compact else 4,
            highlightthickness=1,
            highlightbackground="#e5c3be" if danger else GOLD_LINE if not primary else GOLD,
        )
        button.bind(
            "<Enter>",
            lambda _event, item=button, is_primary=primary, is_danger=danger: self._animate_button(
                item, hovered=True, primary=is_primary, danger=is_danger
            ),
        )
        button.bind(
            "<Leave>",
            lambda _event, item=button, is_primary=primary, is_danger=danger: self._animate_button(
                item, hovered=False, primary=is_primary, danger=is_danger
            ),
        )
        return button

    def _entry(self, parent: tk.Widget, variable: tk.StringVar, placeholder: str = "") -> tk.Entry:
        entry = tk.Entry(
            parent,
            textvariable=variable,
            bg=WHITE,
            fg=INK,
            insertbackground=GOLD_DARK,
            relief="flat",
            justify="right",
            font=(FONT, 9),
            highlightthickness=1,
            highlightbackground=GOLD_LINE,
            highlightcolor=GOLD,
        )
        if placeholder:
            entry.insert(0, placeholder)
            entry.config(fg="#a7a295")

            def focus_in(_event) -> None:
                if entry.get() == placeholder and entry.cget("fg") == "#a7a295":
                    entry.delete(0, "end")
                    entry.config(fg=INK)

            def focus_out(_event) -> None:
                if not entry.get():
                    entry.insert(0, placeholder)
                    entry.config(fg="#a7a295")

            entry.bind("<FocusIn>", focus_in)
            entry.bind("<FocusOut>", focus_out)
        return entry

    def _resize_employee_scroll(self, _event=None) -> None:
        self.employee_canvas.configure(scrollregion=self.employee_canvas.bbox("all"))

    def _resize_employee_canvas(self, event) -> None:
        self.employee_canvas.itemconfigure(self.employee_window, width=event.width)

    def _register_scroll_canvas(self, canvas: tk.Canvas, *related_widgets: tk.Widget) -> None:
        for widget in (canvas, *related_widgets):
            self._scroll_targets[str(widget)] = canvas
        canvas.bind(
            "<Destroy>",
            lambda event, target=canvas: self._forget_scroll_canvas(event, target),
            add="+",
        )

    def _forget_scroll_canvas(self, event, canvas: tk.Canvas) -> None:
        if event.widget is canvas:
            self._scroll_targets = {
                widget_path: target
                for widget_path, target in self._scroll_targets.items()
                if target is not canvas
            }

    def _scroll_canvas_for_widget(self, widget: tk.Widget) -> tk.Canvas | None:
        while widget is not None:
            canvas = self._scroll_targets.get(str(widget))
            if canvas is not None:
                return canvas
            parent = widget.winfo_parent()
            if not parent:
                return None
            widget = widget.nametowidget(parent)
        return None

    def _handle_mousewheel(self, event):
        widget = event.widget
        canvas = self._scroll_canvas_for_widget(widget)
        if canvas is None:
            try:
                pointed_widget = self.root.winfo_containing(event.x_root, event.y_root)
                if pointed_widget is not None:
                    canvas = self._scroll_canvas_for_widget(pointed_widget)
            except tk.TclError:
                return None
        if canvas is None or not canvas.winfo_exists():
            return None

        if getattr(event, "num", None) == 4:
            direction = -1
        elif getattr(event, "num", None) == 5:
            direction = 1
        else:
            delta = getattr(event, "delta", 0)
            if not delta:
                return None
            direction = -1 if delta > 0 else 1
            units = max(1, round(abs(delta) / 120))
            canvas.yview_scroll(direction * units, "units")
            return "break"
        canvas.yview_scroll(direction * 3, "units")
        return "break"

    def change_month(self, offset: int) -> None:
        self.month = shift_month(self.month, offset)
        self.refresh()

    def go_to_current_month(self) -> None:
        self.month = current_month()
        self.refresh()

    def refresh(self) -> None:
        summary = self.store.month_summary(self.month)
        self.month_title.config(text=f"دوره‌ی محاسبه:  {format_month(self.month)}")
        self.summary_values["active_count"].config(text=f"{local_digits(summary['active_count'])} نفر")
        for key in ("salary", "paid", "due"):
            self.summary_values[key].config(text=money(summary[key]))
        self.refresh_payday_banner()
        self.refresh_employees()
        self.refresh_ledger()

    def _due_employee_details(self) -> list[tuple[dict, int, int]]:
        if self.month != current_month():
            return []
        today = date.today()
        jalali_year, jalali_month, jalali_day = jalali_date_from_gregorian(today)
        last_day = jalali_month_length(jalali_year, jalali_month)
        due_employees = []
        for employee in self.store.list_employees():
            due_day = min(employee["pay_day"], last_day)
            if jalali_day < due_day:
                continue
            balance = self.store.employee_totals(employee["id"], self.month)["due"]
            if balance > 0:
                due_employees.append((employee, due_day, balance))
        return due_employees

    def refresh_payday_banner(self) -> None:
        due_employees = self._due_employee_details()
        if not due_employees:
            self.reminder_frame.pack_forget()
            return
        today_day = jalali_date_from_gregorian(date.today())[2]
        due_today = [employee["name"] for employee, day, _balance in due_employees if day == today_day]
        overdue = [
            f"{employee['name']} (روز {day})"
            for employee, day, _balance in due_employees
            if day < today_day
        ]
        messages = []
        if due_today:
            messages.append(f"امروز موعد پرداخت حقوق {', '.join(due_today)} است.")
        if overdue:
            messages.append(f"موعد پرداخت {', '.join(overdue)} گذشته و هنوز مانده دارند.")
        messages.append("برای ثبت یا بررسی پرداخت، از دکمه‌ی «ثبت پرداخت» استفاده کنید.")
        self.reminder_text.configure(text="  ✦  ".join(messages))
        self.reminder_frame.pack(fill="x", pady=(0, 13), after=self.month_bar)
        self.reminder_frame.lift()

    def _check_payday_reminders(self) -> None:
        current = current_month()
        due_employees = self._due_employee_details()
        pending = []
        for employee, day, balance in due_employees:
            reminder_key = f"payday-reminder:{employee['id']}:{current}"
            if self.store.get_setting(reminder_key) is None:
                pending.append((employee, day, balance, reminder_key))
        if pending:
            for _employee, _day, _balance, reminder_key in pending:
                self.store.set_setting(reminder_key, "shown")
            details = "\n".join(
                f"• {employee['name']} — روز پرداخت {day} — مانده {money(balance)}"
                for employee, day, balance, _key in pending
            )
            self.root.after(
                100,
                lambda text=details: messagebox.showinfo(
                    "یادآوری پرداخت حقوق",
                    f"موعد پرداخت ماهانه رسیده است:\n\n{text}",
                    parent=self.root,
                ),
            )
        self.root.after(60_000, self._check_payday_reminders)

    def refresh_employees(self) -> None:
        for child in self.employee_inner.winfo_children():
            child.destroy()
        query = self.employee_filter.get().strip().casefold()
        if query == "جست‌وجوی نام یا سمت".casefold():
            query = ""
        employees = [
            employee
            for employee in self.store.list_employees()
            if query in f"{employee['name']} {employee['role']}".casefold()
        ]
        if not employees:
            message = "هنوز همکاری ثبت نشده است" if not query else "نتیجه‌ای برای جست‌وجوی شما پیدا نشد."
            tk.Label(
                self.employee_inner,
                text=message,
                bg=WHITE,
                fg=MUTED,
                font=(FONT, 10),
                pady=23,
            ).pack(fill="x")
            return

        for employee in employees:
            self._employee_row(employee)

    def _employee_row(self, employee: dict) -> None:
        totals = self.store.employee_totals(employee["id"], self.month)
        archived = employee["archived_month"] is not None
        row = tk.Frame(self.employee_inner, bg=WHITE, highlightthickness=1, highlightbackground="#f0ede6")
        row.pack(fill="x", padx=9, pady=4)
        self._bind_surface_hover(row, normal="#f0ede6", hover="#d3bd8c")

        identity = tk.Frame(row, bg=WHITE)
        identity.pack(side="right", fill="x", expand=True, padx=12, pady=10, anchor="e")
        tk.Label(
            identity,
            text=employee["name"],
            bg=WHITE,
            fg=INK,
            font=(FONT, 10, "bold"),
            anchor="e",
        ).pack(anchor="e")
        subtitle = (
            f"{employee['role']}  ·  پرداخت ماهانه: روز {employee['pay_day']}"
            + (
                f"  ·  شروع همکاری: {self._safe_date(employee['start_date'])}"
                if employee.get("start_date")
                else ""
            )
            + ("  ·  بایگانی‌شده" if archived else "")
        )
        tk.Label(identity, text=subtitle, bg=WHITE, fg=MUTED, font=(FONT, 8), anchor="e").pack(anchor="e", pady=(3, 0))

        self._employee_amount(row, "مانده", max(totals["due"], 0), due=True)
        self._employee_amount(row, "پرداخت‌شده", totals["paid"])
        self._employee_amount(row, "حقوق ماهانه", totals["salary"])
        actions = tk.Frame(row, bg=WHITE)
        actions.pack(side="left", padx=9, pady=9)
        pay_button = self._button(
            actions,
            "ثبت پرداخت",
            lambda selected=employee: self.add_payment(selected),
            primary=True,
        )
        pay_button.pack(side="right", padx=(6, 0))
        if not totals["due"] or archived and self.month > employee["archived_month"]:
            pay_button.config(state="disabled", bg="#d7d3ca", cursor="arrow")
        self._button(
            actions,
            "ویرایش",
            lambda selected=employee: self.edit_employee(selected),
            quiet=True,
        ).pack(side="right")
        self._button(
            actions,
            "فعال‌سازی" if archived else "بایگانی",
            lambda selected=employee: self.toggle_archive(selected),
            quiet=True,
        ).pack(side="right", padx=(6, 0))

    def _employee_amount(self, parent: tk.Widget, label: str, value: int, *, due: bool = False) -> None:
        frame = tk.Frame(parent, bg=WHITE)
        frame.pack(side="right", padx=11, pady=8)
        tk.Label(frame, text=label, bg=WHITE, fg=MUTED, font=(FONT, 7), anchor="e").pack(anchor="e")
        tk.Label(
            frame,
            text=money(value),
            bg=WHITE,
            fg=GOLD_DARK if due and value else INK,
            font=(FONT, 8, "bold"),
            anchor="e",
        ).pack(anchor="e", pady=(4, 0))

    def refresh_ledger(self) -> None:
        for child in self.ledger.winfo_children():
            child.destroy()
        payments = self.store.list_payments(self.month)
        self.payment_count.config(text=f"{len(payments)} پرداخت")
        if not payments:
            tk.Label(
                self.ledger,
                text="برای این ماه هنوز پرداختی ثبت نشده است.",
                bg=WHITE,
                fg=MUTED,
                font=(FONT, 9),
                pady=10,
            ).pack(fill="x")
            return
        for payment in payments:
            self._payment_row(payment)

    def _payment_row(self, payment: dict) -> None:
        row = tk.Frame(self.ledger, bg=WHITE, highlightthickness=1, highlightbackground="#f0ede6")
        row.pack(fill="x", pady=3)
        self._bind_surface_hover(row, normal="#f0ede6", hover="#d3bd8c")
        date_label = self._safe_date(payment["paid_at"])
        detail = f"{payment['role']}   ·   {date_label}   ·   {payment['note'] or 'بدون یادداشت'}"
        identity = tk.Frame(row, bg=WHITE)
        identity.pack(side="right", fill="x", expand=True, padx=12, pady=8, anchor="e")
        tk.Label(
            identity, text=payment["employee_name"], bg=WHITE, fg=INK,
            font=(FONT, 9, "bold"), anchor="e",
        ).pack(anchor="e")
        tk.Label(
            identity, text=detail, bg=WHITE, fg=MUTED, font=(FONT, 8), anchor="e",
        ).pack(anchor="e", pady=(3, 0))
        tk.Label(
            row, text=f"+ {money(payment['amount'])}", bg=WHITE, fg=GREEN,
            font=(FONT, 9, "bold"), anchor="e",
        ).pack(side="right", padx=12)
        self._button(
            row, "حذف", lambda selected=payment: self.delete_payment(selected), quiet=True
        ).pack(side="left", padx=9, pady=7)

    @staticmethod
    def _safe_date(value: str) -> str:
        try:
            return format_jalali_date(date.fromisoformat(value))
        except ValueError:
            return value

    def _employee_dialog(
        self, title: str, employee: dict | None = None
    ) -> tuple[str, str, int, int, str | None] | None:
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.configure(bg=WHITE)
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.grab_set()
        frame = tk.Frame(dialog, bg=WHITE, padx=24, pady=22)
        frame.pack(fill="both", expand=True)
        tk.Label(
            frame, text=title, bg=WHITE, fg=INK, font=(FONT, 15, "bold"), anchor="e"
        ).grid(row=0, column=0, columnspan=2, sticky="e", pady=(0, 17))
        name_var = tk.StringVar(value=employee["name"] if employee else "")
        role_var = tk.StringVar(value=employee["role"] if employee else "پیک")
        salary_var = tk.StringVar(value=str(employee["monthly_salary"]) if employee else "")
        pay_day_var = tk.StringVar(value=str(employee["pay_day"]) if employee else "17")
        start_date_var = tk.StringVar(
            value=(
                self._safe_date(employee["start_date"])
                if employee and employee.get("start_date")
                else format_jalali_date(date.today()) if not employee else ""
            )
        )
        fields = (
            ("نام و نام خانوادگی", name_var),
            ("سمت", role_var),
            ("حقوق ماهانه (تومان)", salary_var),
            ("روز پرداخت ماهانه (1 تا 31)", pay_day_var),
            ("تاریخ شروع همکاری شمسی (سال/ماه/روز)", start_date_var),
        )
        entries: list[tk.Widget] = []
        for index, (label, variable) in enumerate(fields, start=1):
            tk.Label(
                frame, text=label, bg=WHITE, fg=MUTED, font=(FONT, 9), anchor="e"
            ).grid(row=index, column=0, sticky="e", pady=6, padx=(12, 0))
            if label == "سمت":
                control = ttk.Combobox(
                    frame,
                    textvariable=variable,
                    values=("پیک", "آشپز", "کمک‌آشپز", "صندوقدار", "سایر"),
                    state="normal",
                    justify="right",
                    style="Payroll.TCombobox",
                    width=29,
                )
            else:
                control = tk.Entry(
                    frame,
                    textvariable=variable,
                    bg=WHITE,
                    fg=INK,
                    justify="right",
                    relief="flat",
                    font=(FONT, 10),
                    highlightthickness=1,
                    highlightbackground=GOLD_LINE,
                    highlightcolor=GOLD,
                    width=32,
                )
            control.grid(row=index, column=1, sticky="ew", pady=6)
            if label == "حقوق ماهانه (تومان)":
                variable.set(format_grouped_input(variable.get()))
                self._group_amount_entry(control, variable)
            elif label.startswith("روز پرداخت"):
                control.configure(width=8)
            entries.append(control)
        result: list[tuple[str, str, int, int, str | None] | None] = [None]

        def save() -> None:
            try:
                salary = parse_local_integer(salary_var.get())
                if not name_var.get().strip():
                    raise PayrollError("نام کارمند را وارد کنید.")
                if salary <= 0:
                    raise PayrollError("حقوق ماهانه باید بیشتر از صفر باشد.")
                pay_day = parse_local_integer(pay_day_var.get())
                if not 1 <= pay_day <= 31:
                    raise PayrollError("روز پرداخت باید بین 1 و 31 باشد.")
                start_date_text = start_date_var.get().strip()
                start_date = (
                    parse_jalali_date(start_date_text).isoformat() if start_date_text else None
                )
                result[0] = (
                    name_var.get().strip(),
                    role_var.get().strip(),
                    salary,
                    pay_day,
                    start_date,
                )
                dialog.destroy()
            except (ValueError, PayrollError):
                messagebox.showerror(
                    "اطلاعات نامعتبر",
                    "نام، حقوق، روز پرداخت و تاریخ شروع همکاری را بررسی کنید.",
                    parent=dialog,
                )
                entries[0].focus_set()

        actions = tk.Frame(frame, bg=WHITE)
        actions_row = 6
        if employee:
            history = self.store.list_employee_payments(employee["id"])
            history_text = f"{len(history)} پرداخت ثبت‌شده" if history else "هنوز پرداختی ثبت نشده"
            history_section = tk.Frame(frame, bg=GOLD_PALE, padx=11, pady=9)
            history_section.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(14, 0))
            actions_row = 7
            tk.Label(
                history_section,
                text=f"سوابق پرداخت این کارمند · {history_text}",
                bg=GOLD_PALE,
                fg=GOLD_DARK,
                font=(FONT, 9),
                anchor="e",
            ).pack(side="right", padx=(9, 0))
            self._button(
                history_section,
                "مدیریت تراکنش‌ها",
                lambda: self._payment_history_dialog(employee),
                quiet=True,
            ).pack(side="left")
        actions.grid(row=actions_row, column=0, columnspan=2, sticky="ew", pady=(15, 0))
        self._button(actions, "ذخیره اطلاعات", save, primary=True).pack(side="right")
        self._button(actions, "انصراف", dialog.destroy, quiet=True).pack(side="right", padx=(0, 8))
        dialog.bind("<Return>", lambda _event: save())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        entries[0].focus_set()
        self._center_dialog(dialog)
        self.root.wait_window(dialog)
        return result[0]

    def _center_dialog(self, dialog: tk.Toplevel) -> None:
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _group_amount_entry(self, entry: tk.Entry, variable: tk.StringVar) -> None:
        updating = False

        def reformat(*_args) -> None:
            nonlocal updating
            if updating or not entry.winfo_exists():
                return
            original = variable.get()
            cursor = entry.index(tk.INSERT)
            digits_before_cursor = sum(character.isdecimal() for character in original[:cursor])
            formatted = format_grouped_input(original)
            if formatted == original:
                return
            updating = True
            variable.set(formatted)
            updating = False

            position = 0
            seen_digits = 0
            if digits_before_cursor:
                for position, character in enumerate(formatted, start=1):
                    if character.isdecimal():
                        seen_digits += 1
                    if seen_digits >= digits_before_cursor:
                        break
            else:
                position = 0
            entry.after_idle(lambda: entry.icursor(position) if entry.winfo_exists() else None)

        def skip_group_separator(event) -> str | None:
            cursor = entry.index(tk.INSERT)
            value = entry.get()
            if event.keysym == "BackSpace" and cursor > 1 and value[cursor - 1] == ",":
                entry.delete(cursor - 2, cursor - 1)
                return "break"
            if event.keysym == "Delete" and cursor < len(value) - 1 and value[cursor] == ",":
                entry.delete(cursor, cursor + 1)
                return "break"
            return None

        variable.trace_add("write", reformat)
        entry.bind("<KeyPress-BackSpace>", skip_group_separator)
        entry.bind("<KeyPress-Delete>", skip_group_separator)
        entry.bind("<FocusIn>", lambda _event: entry.configure(highlightbackground=GOLD))
        entry.bind("<FocusOut>", lambda _event: entry.configure(highlightbackground=GOLD_LINE))

    def add_employee(self) -> None:
        values = self._employee_dialog("افزودن کارمند")
        if not values:
            return
        try:
            self.store.add_employee(*values)
            self.refresh()
        except (PayrollError, OSError) as error:
            self._show_error(error)

    def edit_employee(self, employee: dict) -> None:
        values = self._employee_dialog("ویرایش اطلاعات کارمند", employee)
        if not values:
            return
        try:
            self.store.update_employee(employee["id"], *values)
            self.refresh()
        except (PayrollError, OSError) as error:
            self._show_error(error)

    def toggle_archive(self, employee: dict) -> None:
        if employee["archived_month"]:
            prompt = f"«{employee['name']}» دوباره فعال شود؟"
            next_archive = None
        else:
            prompt = (
                f"«{employee['name']}» تا پایان {format_month(self.month)} در محاسبه‌ی حقوق می‌ماند "
                "و از ماه‌های بعد بایگانی می‌شود. ادامه می‌دهید؟"
            )
            next_archive = self.month
        if not messagebox.askyesno("وضعیت همکاری", prompt, parent=self.root):
            return
        try:
            self.store.set_archived(employee["id"], next_archive)
            self.refresh()
        except (PayrollError, OSError) as error:
            self._show_error(error)

    def add_payment(self, employee: dict) -> None:
        totals = self.store.employee_totals(employee["id"], self.month)
        if totals["due"] <= 0:
            messagebox.showinfo("حقوق تسویه شده", "برای این کارمند در این ماه مانده‌ای وجود ندارد.", parent=self.root)
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("ثبت پرداخت حقوق")
        dialog.configure(bg=WHITE)
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.grab_set()
        frame = tk.Frame(dialog, bg=WHITE, padx=24, pady=22)
        frame.pack(fill="both", expand=True)
        tk.Label(
            frame, text="ثبت پرداخت مرحله‌ای", bg=WHITE, fg=INK,
            font=(FONT, 15, "bold"), anchor="e",
        ).pack(anchor="e", pady=(0, 10))
        tk.Label(
            frame,
            text=f"{employee['name']}   ·   حقوق {money(totals['salary'])}\nمانده‌ی قابل پرداخت: {money(totals['due'])}",
            bg=GOLD_PALE,
            fg=GOLD_DARK,
            font=(FONT, 9),
            justify="right",
            anchor="e",
            padx=11,
            pady=9,
        ).pack(fill="x", pady=(0, 13))

        amount_var = tk.StringVar()
        paid_date_var = tk.StringVar(value=format_jalali_date(date.today()))
        note_var = tk.StringVar()
        for label, variable in (
            ("مبلغ پرداخت (تومان)", amount_var),
            ("تاریخ پرداخت شمسی (سال/ماه/روز)", paid_date_var),
            ("یادداشت (اختیاری)", note_var),
        ):
            tk.Label(frame, text=label, bg=WHITE, fg=MUTED, font=(FONT, 9), anchor="e").pack(fill="x", pady=(5, 4))
            entry = tk.Entry(
                frame, textvariable=variable, bg=WHITE, fg=INK, justify="right",
                relief="flat", font=(FONT, 10), highlightthickness=1,
                highlightbackground=GOLD_LINE, highlightcolor=GOLD,
            )
            entry.pack(fill="x", ipady=8)
            if label.startswith("مبلغ پرداخت"):
                self._group_amount_entry(entry, variable)
                entry.focus_set()

        def save() -> None:
            try:
                amount = parse_local_integer(amount_var.get())
                paid_at = parse_jalali_date(paid_date_var.get()).isoformat()
                self.store.add_payment(employee["id"], self.month, amount, paid_at, note_var.get())
                dialog.destroy()
                self.refresh()
            except (ValueError, PayrollError) as error:
                messagebox.showerror("پرداخت ثبت نشد", str(error), parent=dialog)

        actions = tk.Frame(frame, bg=WHITE)
        actions.pack(fill="x", pady=(15, 0))
        self._button(actions, "ثبت پرداخت", save, primary=True).pack(side="right")
        self._button(actions, "انصراف", dialog.destroy, quiet=True).pack(side="right", padx=(0, 8))
        dialog.bind("<Return>", lambda _event: save())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self._center_dialog(dialog)

    def delete_payment(
        self,
        payment: dict,
        *,
        parent: tk.Misc | None = None,
        after_delete=None,
    ) -> None:
        parent = parent or self.root
        question = f"پرداخت {money(payment['amount'])} به {payment['employee_name']} حذف شود؟"
        if not messagebox.askyesno("حذف پرداخت", question, parent=parent, icon="warning"):
            return
        try:
            self.store.delete_payment(payment["id"])
            self.refresh()
            if after_delete:
                after_delete()
        except (PayrollError, OSError) as error:
            messagebox.showerror("خطا در ذخیره‌ی اطلاعات", str(error), parent=parent)

    def _edit_payment_dialog(self, payment: dict, parent: tk.Misc, after_save) -> None:
        dialog = tk.Toplevel(parent)
        dialog.title("ویرایش پرداخت")
        dialog.configure(bg=WHITE)
        dialog.transient(parent)
        dialog.resizable(False, False)
        dialog.grab_set()
        frame = tk.Frame(dialog, bg=WHITE, padx=22, pady=20)
        frame.pack(fill="both", expand=True)
        tk.Label(
            frame,
            text=f"ویرایش پرداخت · {payment['employee_name']}",
            bg=WHITE,
            fg=INK,
            font=(FONT, 13, "bold"),
            anchor="e",
        ).pack(fill="x", pady=(0, 12))
        amount_var = tk.StringVar(value=format_grouped_input(str(payment["amount"])))
        date_var = tk.StringVar(value=self._safe_date(payment["paid_at"]))
        note_var = tk.StringVar(value=payment["note"])
        for label, variable in (
            ("مبلغ پرداخت (تومان)", amount_var),
            ("تاریخ پرداخت شمسی (سال/ماه/روز)", date_var),
            ("یادداشت", note_var),
        ):
            tk.Label(frame, text=label, bg=WHITE, fg=MUTED, font=(FONT, 9), anchor="e").pack(
                fill="x", pady=(5, 4)
            )
            entry = tk.Entry(
                frame,
                textvariable=variable,
                bg=WHITE,
                fg=INK,
                justify="right",
                relief="flat",
                font=(FONT, 10),
                highlightthickness=1,
                highlightbackground=GOLD_LINE,
                highlightcolor=GOLD,
            )
            entry.pack(fill="x", ipady=8)
            if label.startswith("مبلغ"):
                self._group_amount_entry(entry, variable)
                entry.focus_set()

        def save() -> None:
            try:
                amount = parse_local_integer(amount_var.get())
                paid_at = parse_jalali_date(date_var.get()).isoformat()
                self.store.update_payment(
                    payment["id"], amount, paid_at, note_var.get()
                )
                dialog.destroy()
                self.refresh()
                after_save()
            except (ValueError, PayrollError, OSError) as error:
                messagebox.showerror("پرداخت ذخیره نشد", str(error), parent=dialog)

        actions = tk.Frame(frame, bg=WHITE)
        actions.pack(fill="x", pady=(15, 0))
        self._button(actions, "ذخیره تغییرات", save, primary=True).pack(side="right")
        self._button(actions, "انصراف", dialog.destroy, quiet=True).pack(side="right", padx=(0, 8))
        dialog.bind("<Return>", lambda _event: save())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self._center_dialog(dialog)

    def _payment_history_dialog(self, employee: dict) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title(f"تراکنش‌های {employee['name']}")
        dialog.configure(bg=WHITE)
        dialog.transient(self.root)
        dialog.geometry("700x480")
        dialog.minsize(520, 320)
        dialog.grab_set()
        frame = tk.Frame(dialog, bg=WHITE, padx=18, pady=16)
        frame.pack(fill="both", expand=True)
        heading = tk.Frame(frame, bg=WHITE)
        heading.pack(fill="x", pady=(0, 12))
        tk.Label(
            heading,
            text=f"سوابق پرداخت · {employee['name']}",
            bg=WHITE,
            fg=INK,
            font=(FONT, 13, "bold"),
            anchor="e",
        ).pack(side="right")
        count_label = tk.Label(heading, text="", bg=WHITE, fg=MUTED, font=(FONT, 9))
        count_label.pack(side="left")
        canvas = tk.Canvas(frame, bg=WHITE, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="left", fill="y")
        canvas.pack(side="right", fill="both", expand=True)
        rows = tk.Frame(canvas, bg=WHITE)
        window = canvas.create_window((0, 0), window=rows, anchor="nw")
        rows.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        self._register_scroll_canvas(canvas, rows, scrollbar)

        def render() -> None:
            for child in rows.winfo_children():
                child.destroy()
            history = self.store.list_employee_payments(employee["id"])
            count_label.configure(text=f"{len(history)} پرداخت")
            if not history:
                tk.Label(
                    rows, text="برای این کارمند پرداختی ثبت نشده است.",
                    bg=WHITE, fg=MUTED, font=(FONT, 10), pady=24,
                ).pack(fill="x")
                return
            for payment in history:
                payment_for_edit = {**payment, "employee_name": employee["name"]}
                row = tk.Frame(
                    rows, bg=WHITE, highlightthickness=1, highlightbackground=GOLD_LINE
                )
                row.pack(fill="x", pady=4)
                details = tk.Frame(row, bg=WHITE)
                details.pack(side="right", fill="x", expand=True, padx=12, pady=9)
                tk.Label(
                    details,
                    text=f"{format_month(payment['payroll_month'])}  ·  {self._safe_date(payment['paid_at'])}",
                    bg=WHITE,
                    fg=INK,
                    font=(FONT, 9, "bold"),
                    anchor="e",
                ).pack(anchor="e")
                tk.Label(
                    details,
                    text=payment["note"] or "بدون یادداشت",
                    bg=WHITE,
                    fg=MUTED,
                    font=(FONT, 8),
                    anchor="e",
                ).pack(anchor="e", pady=(3, 0))
                tk.Label(
                    row,
                    text=money(payment["amount"]),
                    bg=WHITE,
                    fg=GREEN,
                    font=(FONT, 9, "bold"),
                ).pack(side="right", padx=12)
                controls = tk.Frame(row, bg=WHITE)
                controls.pack(side="left", padx=8, pady=7)
                self._button(
                    controls,
                    "ویرایش",
                    lambda item=payment_for_edit: self._edit_payment_dialog(
                        item, dialog, render
                    ),
                    quiet=True,
                ).pack(side="right", padx=(0, 5))
                self._button(
                    controls,
                    "حذف تراکنش",
                    lambda item=payment: self.delete_payment(
                        item, parent=dialog, after_delete=render
                    ),
                    danger=True,
                ).pack(side="right")

        render()
        self._button(frame, "بستن", dialog.destroy, quiet=True).pack(anchor="w", pady=(10, 0))
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self._center_dialog(dialog)

    def _show_error(self, error: Exception) -> None:
        messagebox.showerror("خطا در ذخیره‌ی اطلاعات", str(error), parent=self.root)

    @staticmethod
    def _jalali_month_range(month: str) -> tuple[date, date]:
        year, number = (int(value) for value in month.split("-"))
        start = gregorian_date_from_jalali(year, number, 1)
        next_year, next_month = shift_jalali_month(year, number, 1)
        end = gregorian_date_from_jalali(next_year, next_month, 1)
        return start, end

    @staticmethod
    def _week_range(reference: date) -> tuple[date, date]:
        days_since_saturday = (reference.weekday() + 2) % 7
        start = reference - timedelta(days=days_since_saturday)
        return start, start + timedelta(days=7)

    def open_expenses(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("هزینه‌های کترینگ")
        dialog.configure(bg=PAPER)
        dialog.transient(self.root)
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        dialog_width = min(1120, max(680, screen_width - 60))
        dialog_height = min(820, max(540, screen_height - 80))
        dialog.geometry(f"{dialog_width}x{dialog_height}")
        dialog.minsize(min(760, dialog_width), min(560, dialog_height))
        dialog.grab_set()
        shell = tk.Frame(dialog, bg=PAPER, padx=18, pady=14)
        shell.pack(fill="both", expand=True)

        heading = tk.Frame(shell, bg=PAPER)
        heading.pack(fill="x", pady=(0, 9))
        title_box = tk.Frame(heading, bg=PAPER)
        title_box.pack(side="right")
        tk.Label(
            title_box,
            text="دفتر هزینه‌های کترینگ",
            bg=PAPER,
            fg=INK,
            font=(FONT, 17, "bold"),
            anchor="e",
        ).pack(anchor="e")
        tk.Label(
            title_box,
            text="خریدها، اجاره و سایر هزینه‌ها را ثبت و مقایسه کنید.",
            bg=PAPER,
            fg=MUTED,
            font=(FONT, 9),
            anchor="e",
        ).pack(anchor="e", pady=(3, 0))
        self._button(heading, "بستن", dialog.destroy, quiet=True).pack(side="left", pady=5)

        page = tk.Frame(shell, bg=PAPER)
        page.pack(fill="both", expand=True)
        page_canvas = tk.Canvas(page, bg=PAPER, highlightthickness=0, bd=0)
        page_scrollbar = ttk.Scrollbar(page, orient="vertical", command=page_canvas.yview)
        page_canvas.configure(yscrollcommand=page_scrollbar.set)
        page_scrollbar.pack(side="left", fill="y", padx=(0, 2))
        page_canvas.pack(side="right", fill="both", expand=True)
        page_content = tk.Frame(page_canvas, bg=PAPER)
        page_window = page_canvas.create_window((0, 0), window=page_content, anchor="nw")
        page_content.bind(
            "<Configure>",
            lambda _event: page_canvas.configure(scrollregion=page_canvas.bbox("all")),
        )
        page_canvas.bind(
            "<Configure>",
            lambda event: page_canvas.itemconfigure(page_window, width=event.width),
        )
        self._register_scroll_canvas(page_canvas, page_content, page_scrollbar)

        totals_frame = tk.Frame(page_content, bg=PAPER)
        totals_frame.pack(fill="x", pady=(0, 8))
        today_card = self._panel(totals_frame)
        month_card = self._panel(totals_frame)
        today_card.pack(side="right", fill="x", expand=True, padx=(0, 6))
        month_card.pack(side="right", fill="x", expand=True, padx=(6, 0))
        tk.Label(
            today_card, text="جمع هزینه‌های امروز", bg=WHITE, fg=MUTED,
            font=(FONT, 9), anchor="e",
        ).pack(fill="x", padx=14, pady=(10, 3))
        today_total_label = tk.Label(
            today_card, text="", bg=WHITE, fg=INK, font=(FONT, 15, "bold"), anchor="e"
        )
        today_total_label.pack(fill="x", padx=14, pady=(0, 10))
        tk.Label(
            month_card, text="جمع هزینه‌های این ماه", bg=WHITE, fg=MUTED,
            font=(FONT, 9), anchor="e",
        ).pack(fill="x", padx=14, pady=(10, 3))
        month_total_label = tk.Label(
            month_card, text="", bg=WHITE, fg=GOLD_DARK, font=(FONT, 15, "bold"), anchor="e"
        )
        month_total_label.pack(fill="x", padx=14, pady=(0, 10))

        form = self._panel(page_content)
        form.pack(fill="x", pady=(0, 8))
        tk.Label(
            form, text="ثبت هزینه‌ی جدید", bg=WHITE, fg=INK,
            font=(FONT, 11, "bold"), anchor="e",
        ).pack(fill="x", padx=13, pady=(10, 7))
        fields = tk.Frame(form, bg=WHITE)
        fields.pack(fill="x", padx=12, pady=(0, 11))
        description_var = tk.StringVar()
        amount_var = tk.StringVar()
        date_var = tk.StringVar(value=format_jalali_date(date.today()))
        controls: list[tk.Widget] = []
        for column, (label, variable, width) in enumerate(
            (
                ("شرح / یادداشت (مثلاً گوشت، مرغ، نوشابه، اجاره)", description_var, 34),
                ("مبلغ (تومان)", amount_var, 18),
                ("تاریخ شمسی", date_var, 14),
            )
        ):
            section = tk.Frame(fields, bg=WHITE)
            section.grid(row=0, column=column, sticky="ew", padx=5)
            fields.grid_columnconfigure(column, weight=(3 if column == 0 else 1))
            tk.Label(
                section, text=label, bg=WHITE, fg=MUTED, font=(FONT, 8), anchor="e"
            ).pack(fill="x", pady=(0, 4))
            entry = tk.Entry(
                section,
                textvariable=variable,
                bg=WHITE,
                fg=INK,
                justify="right",
                relief="flat",
                font=(FONT, 9),
                width=width,
                highlightthickness=1,
                highlightbackground=GOLD_LINE,
                highlightcolor=GOLD,
            )
            entry.pack(fill="x", ipady=7)
            controls.append(entry)
            if column == 1:
                self._group_amount_entry(entry, variable)
        self._button(fields, "ثبت هزینه", lambda: save_expense(), primary=True).grid(
            row=0, column=3, padx=(5, 2), sticky="sew"
        )

        charts = tk.Frame(page_content, bg=PAPER)
        charts.pack(fill="x", pady=(0, 8))
        week_panel = self._panel(charts)
        month_panel = self._panel(charts)
        week_panel.pack(side="right", fill="x", expand=True, padx=(0, 6))
        month_panel.pack(side="right", fill="x", expand=True, padx=(6, 0))
        tk.Label(
            week_panel, text="مقایسه‌ی هفتگی", bg=WHITE, fg=INK,
            font=(FONT, 10, "bold"), anchor="e",
        ).pack(fill="x", padx=12, pady=(9, 0))
        tk.Label(
            month_panel, text="مقایسه‌ی ماهانه", bg=WHITE, fg=INK,
            font=(FONT, 10, "bold"), anchor="e",
        ).pack(fill="x", padx=12, pady=(9, 0))
        week_chart = tk.Canvas(week_panel, height=124, bg=WHITE, highlightthickness=0)
        month_chart = tk.Canvas(month_panel, height=124, bg=WHITE, highlightthickness=0)
        week_chart.pack(fill="x", padx=8, pady=(1, 7))
        month_chart.pack(fill="x", padx=8, pady=(1, 7))

        ledger = self._panel(page_content)
        ledger.pack(fill="x")
        ledger_heading = tk.Frame(ledger, bg=WHITE)
        ledger_heading.pack(fill="x", padx=13, pady=(10, 5))
        tk.Label(
            ledger_heading, text=f"هزینه‌های {format_month(current_month())}",
            bg=WHITE, fg=INK, font=(FONT, 10, "bold"), anchor="e",
        ).pack(side="right")
        entry_count = tk.Label(ledger_heading, text="", bg=WHITE, fg=MUTED, font=(FONT, 8))
        entry_count.pack(side="left")
        expense_rows = tk.Frame(ledger, bg=WHITE)
        expense_rows.pack(fill="x", padx=12, pady=(0, 10))

        def draw_comparison(
            chart: tk.Canvas,
            current_label: str,
            current_value: int,
            previous_label: str,
            previous_value: int,
        ) -> None:
            chart.delete("all")
            width = max(chart.winfo_width(), 360)
            bar_start = 115
            bar_end = width - 105
            bar_width = max(100, bar_end - bar_start)
            max_value = max(current_value, previous_value, 1)
            for index, (label, value, color) in enumerate(
                ((current_label, current_value, GOLD), (previous_label, previous_value, "#c9c3b7"))
            ):
                y = 51 + index * 58
                chart.create_text(
                    width - 8, y + 9, text=label, fill=INK, anchor="e", font=(FONT, 8)
                )
                chart.create_rectangle(
                    bar_start, y, bar_end, y + 19, fill="#f4f1ea", outline=""
                )
                filled = int(bar_width * value / max_value) if value else 0
                if filled:
                    chart.create_rectangle(
                        bar_end - filled, y, bar_end, y + 19, fill=color, outline=""
                    )
                chart.create_text(
                    8, y + 9, text=money(value), fill=MUTED, anchor="w", font=(FONT, 7)
                )

        def render_charts() -> None:
            today = date.today()
            week_start, week_end = self._week_range(today)
            previous_week_start = week_start - timedelta(days=7)
            draw_comparison(
                week_chart,
                "این هفته",
                self.store.expense_total(week_start.isoformat(), week_end.isoformat()),
                "هفته‌ی قبل",
                self.store.expense_total(previous_week_start.isoformat(), week_start.isoformat()),
            )
            month_start, month_end = self._jalali_month_range(current_month())
            year, month_number, _day = jalali_date_from_gregorian(today)
            previous_month = shift_month(f"{year:04d}-{month_number:02d}", -1)
            previous_start, _previous_end = self._jalali_month_range(previous_month)
            draw_comparison(
                month_chart,
                "این ماه",
                self.store.expense_total(month_start.isoformat(), month_end.isoformat()),
                "ماه قبل",
                self.store.expense_total(previous_start.isoformat(), month_start.isoformat()),
            )

        def render() -> None:
            today = date.today()
            today_start = today.isoformat()
            today_end = (today + timedelta(days=1)).isoformat()
            month_start, month_end = self._jalali_month_range(current_month())
            today_total_label.config(text=money(self.store.expense_total(today_start, today_end)))
            month_total_label.config(
                text=money(self.store.expense_total(month_start.isoformat(), month_end.isoformat()))
            )

            render_charts()

            for child in expense_rows.winfo_children():
                child.destroy()
            expenses = self.store.list_expenses(month_start.isoformat(), month_end.isoformat())
            entry_count.config(text=f"{len(expenses)} مورد")
            if not expenses:
                tk.Label(
                    expense_rows,
                    text="برای این ماه هنوز هزینه‌ای ثبت نشده است.",
                    bg=WHITE,
                    fg=MUTED,
                    font=(FONT, 9),
                    pady=20,
                ).pack(fill="x")
                return
            grouped: dict[str, list[dict]] = {}
            for expense in expenses:
                grouped.setdefault(expense["spent_at"], []).append(expense)
            for expense_date, daily_expenses in grouped.items():
                day_header = tk.Frame(expense_rows, bg=GOLD_PALE)
                day_header.pack(fill="x", pady=(5, 2))
                tk.Label(
                    day_header,
                    text=self._safe_date(expense_date),
                    bg=GOLD_PALE,
                    fg=GOLD_DARK,
                    font=(FONT, 9, "bold"),
                    anchor="e",
                ).pack(side="right", padx=10, pady=6)
                daily_total = sum(item["amount"] for item in daily_expenses)
                tk.Label(
                    day_header,
                    text=f"جمع روز: {money(daily_total)}",
                    bg=GOLD_PALE,
                    fg=GOLD_DARK,
                    font=(FONT, 8, "bold"),
                ).pack(side="left", padx=10)
                for expense in daily_expenses:
                    row = tk.Frame(
                        expense_rows,
                        bg=WHITE,
                        highlightthickness=1,
                        highlightbackground="#f0ede6",
                    )
                    row.pack(fill="x", pady=2)
                    tk.Label(
                        row,
                        text=expense["description"],
                        bg=WHITE,
                        fg=INK,
                        font=(FONT, 9),
                        anchor="e",
                    ).pack(side="right", fill="x", expand=True, padx=12, pady=8)
                    tk.Label(
                        row,
                        text=money(expense["amount"]),
                        bg=WHITE,
                        fg=GOLD_DARK,
                        font=(FONT, 9, "bold"),
                    ).pack(side="right", padx=10)
                    self._button(
                        row,
                        "ویرایش",
                        lambda item=expense: edit_expense(item),
                        quiet=True,
                        compact=True,
                    ).pack(side="left", padx=3, pady=5)
                    self._button(
                        row,
                        "حذف",
                        lambda item=expense: delete_expense(item),
                        danger=True,
                        compact=True,
                    ).pack(side="left", padx=(3, 8), pady=5)

        def save_expense() -> None:
            try:
                self.store.add_expense(
                    description_var.get(),
                    parse_local_integer(amount_var.get()),
                    parse_jalali_date(date_var.get()).isoformat(),
                )
                description_var.set("")
                amount_var.set("")
                date_var.set(format_jalali_date(date.today()))
                render()
            except (ValueError, PayrollError, OSError) as error:
                messagebox.showerror("هزینه ثبت نشد", str(error), parent=dialog)

        def edit_expense(expense: dict) -> None:
            edit_dialog = tk.Toplevel(dialog)
            edit_dialog.title("ویرایش هزینه")
            edit_dialog.configure(bg=WHITE)
            edit_dialog.transient(dialog)
            edit_dialog.resizable(False, False)
            edit_dialog.grab_set()
            frame = tk.Frame(edit_dialog, bg=WHITE, padx=22, pady=18)
            frame.pack(fill="both", expand=True)
            description_value = tk.StringVar(value=expense["description"])
            amount_value = tk.StringVar(value=format_grouped_input(str(expense["amount"])))
            date_value = tk.StringVar(value=self._safe_date(expense["spent_at"]))
            edit_entries = []
            for label, variable in (
                ("شرح / یادداشت", description_value),
                ("مبلغ (تومان)", amount_value),
                ("تاریخ شمسی", date_value),
            ):
                tk.Label(
                    frame, text=label, bg=WHITE, fg=MUTED, font=(FONT, 9), anchor="e"
                ).pack(fill="x", pady=(5, 4))
                entry = tk.Entry(
                    frame, textvariable=variable, bg=WHITE, fg=INK, justify="right",
                    relief="flat", font=(FONT, 10), highlightthickness=1,
                    highlightbackground=GOLD_LINE, highlightcolor=GOLD,
                )
                entry.pack(fill="x", ipady=7)
                edit_entries.append(entry)
                if label.startswith("مبلغ"):
                    self._group_amount_entry(entry, variable)

            def save_edit() -> None:
                try:
                    self.store.update_expense(
                        expense["id"],
                        description_value.get(),
                        parse_local_integer(amount_value.get()),
                        parse_jalali_date(date_value.get()).isoformat(),
                    )
                    edit_dialog.destroy()
                    render()
                except (ValueError, PayrollError, OSError) as error:
                    messagebox.showerror("هزینه ذخیره نشد", str(error), parent=edit_dialog)

            actions = tk.Frame(frame, bg=WHITE)
            actions.pack(fill="x", pady=(14, 0))
            self._button(actions, "ذخیره تغییرات", save_edit, primary=True).pack(side="right")
            self._button(actions, "انصراف", edit_dialog.destroy, quiet=True).pack(
                side="right", padx=(0, 7)
            )
            edit_dialog.bind("<Return>", lambda _event: save_edit())
            edit_dialog.bind("<Escape>", lambda _event: edit_dialog.destroy())
            self._center_dialog(edit_dialog)

        def delete_expense(expense: dict) -> None:
            if not messagebox.askyesno(
                "حذف هزینه",
                f"هزینه‌ی «{expense['description']}» به مبلغ {money(expense['amount'])} حذف شود؟",
                parent=dialog,
                icon="warning",
            ):
                return
            try:
                self.store.delete_expense(expense["id"])
                render()
            except (PayrollError, OSError) as error:
                messagebox.showerror("هزینه حذف نشد", str(error), parent=dialog)

        week_chart.bind("<Configure>", lambda _event: render_charts())
        month_chart.bind("<Configure>", lambda _event: render_charts())
        render()
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self._center_dialog(dialog)

    def close(self) -> None:
        self.store.close()
        self.root.destroy()


def main() -> None:
    data_directory = application_data_directory()
    try:
        store = PayrollStore(data_directory / "payroll.sqlite3")
    except (OSError, PermissionError) as error:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("خطا در ذخیره‌سازی", f"پوشه‌ی اطلاعات برنامه قابل استفاده نیست:\n{error}")
        root.destroy()
        return

    root = tk.Tk()
    PayrollApp(root, store)
    root.mainloop()


if __name__ == "__main__":
    main()
