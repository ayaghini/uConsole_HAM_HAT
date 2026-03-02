#!/usr/bin/env python3
"""CommsTab — Contacts, Groups, Chat Threads, Intro Discovery.

Layout:
  Left panel  : Contacts & Groups management, Heard stations, Intro config
  Right panel : Thread list (top) + active thread messages (middle) + compose (bottom)
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import TYPE_CHECKING, Optional

from ..engine.models import ChatMessage
from .widgets import BoundedLog, add_row, scrollable_frame

if TYPE_CHECKING:
    from ..app import HamHatApp


class CommsTab(ttk.Frame):
    """Chat & comms management tab."""

    def __init__(self, parent: ttk.Notebook, app: "HamHatApp") -> None:
        super().__init__(parent)
        self._app = app
        self._build()

    # ------------------------------------------------------------------
    # Build layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.columnconfigure(0, weight=0, minsize=260)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        left = ttk.Frame(self, padding=(6, 6, 4, 6))
        left.grid(row=0, column=0, sticky="nsew")
        right = ttk.Frame(self, padding=(4, 6, 6, 6))
        right.grid(row=0, column=1, sticky="nsew")

        self._build_left(left)
        self._build_right(right)

    # ------------------------------------------------------------------
    # Left panel
    # ------------------------------------------------------------------

    def _build_left(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        row = 0

        # ---- Contacts ----
        lf = ttk.LabelFrame(parent, text="Contacts", padding=6)
        lf.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        lf.columnconfigure(0, weight=1)
        row += 1

        self._contacts_lb = tk.Listbox(lf, height=6, exportselection=False, font=("Consolas", 9))
        self._contacts_lb.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))

        btn_row = ttk.Frame(lf)
        btn_row.grid(row=1, column=0, columnspan=2, sticky="ew")
        ttk.Button(btn_row, text="Add…", command=self._add_contact, width=8).pack(side="left", padx=(0, 2))
        ttk.Button(btn_row, text="Remove", command=self._remove_contact, width=8).pack(side="left", padx=2)
        ttk.Button(btn_row, text="← Heard", command=self._import_heard_to_contacts, width=8).pack(side="left", padx=2)

        # ---- Groups ----
        gf = ttk.LabelFrame(parent, text="Groups", padding=6)
        gf.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        gf.columnconfigure(0, weight=1)
        row += 1

        self._groups_lb = tk.Listbox(gf, height=5, exportselection=False, font=("Consolas", 9))
        self._groups_lb.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        self._groups_lb.bind("<<ListboxSelect>>", self._on_group_select)

        btn_row2 = ttk.Frame(gf)
        btn_row2.grid(row=1, column=0, columnspan=2, sticky="ew")
        ttk.Button(btn_row2, text="New…", command=self._new_group, width=8).pack(side="left", padx=(0, 2))
        ttk.Button(btn_row2, text="Edit…", command=self._edit_group, width=8).pack(side="left", padx=2)
        ttk.Button(btn_row2, text="Delete", command=self._delete_group, width=8).pack(side="left", padx=2)

        self._group_members_var = tk.StringVar(value="")
        ttk.Label(gf, textvariable=self._group_members_var, foreground="#9cc4dd",
                  font=("Consolas", 8), wraplength=230).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # ---- Heard Stations ----
        hf = ttk.LabelFrame(parent, text="Heard Stations", padding=6)
        hf.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        hf.columnconfigure(0, weight=1)
        row += 1

        self._heard_lb = tk.Listbox(hf, height=5, exportselection=False, font=("Consolas", 9))
        self._heard_lb.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        ttk.Button(hf, text="Clear Heard", command=self._clear_heard).grid(row=1, column=0, sticky="w")

        # ---- Intro / Discovery ----
        inf = ttk.LabelFrame(parent, text="Intro / Discovery", padding=6)
        inf.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        inf.columnconfigure(1, weight=1)
        row += 1

        self._intro_note_var = tk.StringVar(value="uConsole HAM HAT online")
        add_row(inf, "Note:", ttk.Entry(inf, textvariable=self._intro_note_var), row=0)
        ttk.Button(inf, text="Send Intro Packet", command=self._send_intro).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))

    # ------------------------------------------------------------------
    # Right panel
    # ------------------------------------------------------------------

    def _build_right(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # ---- Thread selector ----
        tf = ttk.LabelFrame(parent, text="Threads", padding=6)
        tf.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        tf.columnconfigure(0, weight=1)

        self._threads_lb = tk.Listbox(tf, height=4, exportselection=False, font=("Consolas", 9))
        self._threads_lb.grid(row=0, column=0, sticky="ew")
        self._threads_lb.bind("<<ListboxSelect>>", self._on_thread_select)

        # ---- Message area ----
        mf = ttk.LabelFrame(parent, text="Messages", padding=6)
        mf.grid(row=1, column=0, sticky="nsew", pady=(0, 6))
        mf.columnconfigure(0, weight=1)
        mf.rowconfigure(0, weight=1)

        self._msg_log = BoundedLog(mf, state="disabled", wrap="word",
                                    font=("Consolas", 9), background="#0f2531",
                                    foreground="#d9edf7", height=14)
        self._msg_log.grid(row=0, column=0, sticky="nsew")

        # Colour tags
        self._msg_log.tag_configure("tx", foreground="#7ec8e3")
        self._msg_log.tag_configure("rx", foreground="#f5a623")
        self._msg_log.tag_configure("sys", foreground="#9cc4dd")

        # ---- Compose area ----
        cf = ttk.LabelFrame(parent, text="Send Message", padding=6)
        cf.grid(row=2, column=0, sticky="ew")
        cf.columnconfigure(1, weight=1)

        # To / Group selector
        ttk.Label(cf, text="To:").grid(row=0, column=0, sticky="w", pady=2)
        self._to_var = tk.StringVar()
        self._to_combo = ttk.Combobox(cf, textvariable=self._to_var, state="normal", width=20,
                                      font=("Consolas", 9))
        self._to_combo.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=2)

        ttk.Label(cf, text="Text:").grid(row=1, column=0, sticky="nw", pady=2)
        self._compose_text = tk.Text(cf, height=3, wrap="word", font=("Consolas", 9))
        self._compose_text.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=2)
        self._compose_text.bind("<Return>", self._on_compose_enter)
        self._compose_text.bind("<Shift-Return>", lambda _e: None)  # allow newline with shift

        btn_row = ttk.Frame(cf)
        btn_row.grid(row=2, column=0, columnspan=2, sticky="e", pady=(4, 0))
        self._reliable_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(btn_row, text="Reliable", variable=self._reliable_var).pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="Send", command=self._send_message).pack(side="left")

    # ------------------------------------------------------------------
    # Contacts management
    # ------------------------------------------------------------------

    def _add_contact(self) -> None:
        call = simpledialog.askstring("Add Contact", "Callsign:", parent=self)
        if call:
            self._app.add_contact(call)

    def _remove_contact(self) -> None:
        sel = self._contacts_lb.curselection()
        if not sel:
            return
        call = self._contacts_lb.get(sel[0])
        if messagebox.askyesno("Remove Contact", f"Remove {call}?", parent=self):
            self._app.remove_contact(call)

    def _import_heard_to_contacts(self) -> None:
        self._app.import_heard_to_contacts()

    def _clear_heard(self) -> None:
        self._app.clear_heard()

    # ------------------------------------------------------------------
    # Group management
    # ------------------------------------------------------------------

    def _new_group(self) -> None:
        name = simpledialog.askstring("New Group", "Group name:", parent=self)
        if not name:
            return
        members_str = simpledialog.askstring(
            "Group Members",
            "Members (comma-separated callsigns):",
            parent=self,
        )
        if members_str is None:
            return
        members = [m.strip() for m in members_str.split(",") if m.strip()]
        self._app.set_group(name, members)

    def _edit_group(self) -> None:
        sel = self._groups_lb.curselection()
        if not sel:
            return
        text = self._groups_lb.get(sel[0])
        name = text.split(" ")[0]
        groups = self._app.comms.groups
        current = groups.get(name, [])
        members_str = simpledialog.askstring(
            "Edit Group Members",
            f"Members of {name} (comma-separated):",
            initialvalue=", ".join(current),
            parent=self,
        )
        if members_str is None:
            return
        members = [m.strip() for m in members_str.split(",") if m.strip()]
        self._app.set_group(name, members)

    def _delete_group(self) -> None:
        sel = self._groups_lb.curselection()
        if not sel:
            return
        text = self._groups_lb.get(sel[0])
        name = text.split(" ")[0]
        if messagebox.askyesno("Delete Group", f"Delete group {name}?", parent=self):
            self._app.delete_group(name)

    def _on_group_select(self, _e: tk.Event) -> None:
        sel = self._groups_lb.curselection()
        if not sel:
            self._group_members_var.set("")
            return
        text = self._groups_lb.get(sel[0])
        name = text.split(" ")[0]
        groups = self._app.comms.groups
        members = groups.get(name, [])
        self._group_members_var.set("Members: " + ", ".join(members) if members else "No members")

    # ------------------------------------------------------------------
    # Intro
    # ------------------------------------------------------------------

    def _send_intro(self) -> None:
        self._app.send_intro(self._intro_note_var.get())

    # ------------------------------------------------------------------
    # Thread & message handling
    # ------------------------------------------------------------------

    def _on_thread_select(self, _e: tk.Event) -> None:
        sel = self._threads_lb.curselection()
        if not sel:
            return
        thread_key = self._threads_lb.get(sel[0]).split("  ")[0].strip()
        self._app.comms.set_active_thread(thread_key)
        self._load_thread(thread_key)
        # Auto-populate To: field
        if thread_key.startswith("GROUP:"):
            group_name = thread_key[6:]
            self._to_var.set(f"@{group_name}")
        else:
            self._to_var.set(thread_key)
        self._refresh_thread_list()

    def _load_thread(self, thread_key: str) -> None:
        msgs = self._app.comms.messages_for_thread(thread_key)
        self._msg_log.configure(state="normal")
        self._msg_log.delete("1.0", "end")
        for msg in msgs:
            self._render_message(msg)
        self._msg_log.configure(state="disabled")
        self._msg_log.see("end")

    def _render_message(self, msg: ChatMessage) -> None:
        """Append a single message to the log with colour tagging."""
        ts = getattr(msg, "ts", "")
        if msg.direction == "TX":
            prefix = f"[TX] {msg.src} → {msg.dst}: "
            tag = "tx"
        elif msg.direction == "RX":
            prefix = f"[RX] {msg.src}: "
            tag = "rx"
        else:
            prefix = f"[SYS] "
            tag = "sys"
        line = prefix + msg.text + "\n"
        self._msg_log.configure(state="normal")
        self._msg_log.insert("end", line, (tag,))
        self._msg_log.configure(state="disabled")
        self._msg_log.see("end")

    def _on_compose_enter(self, event: tk.Event) -> str:
        """Send on Enter (not Shift+Enter)."""
        if not (event.state & 0x1):  # shift not held
            self._send_message()
            return "break"
        return ""  # allow newline

    def _send_message(self) -> None:
        to = self._to_var.get().strip()
        text = self._compose_text.get("1.0", "end-1c").strip()
        if not to or not text:
            return
        reliable = self._reliable_var.get()
        if to.startswith("@"):
            group = to[1:]
            self._app.send_group_message(group, text)
        else:
            self._app.send_direct_message(to, text, reliable=reliable)
        self._compose_text.delete("1.0", "end")

    # ------------------------------------------------------------------
    # Public update methods (called from app event dispatcher)
    # ------------------------------------------------------------------

    def on_message(self, msg: ChatMessage) -> None:
        """Called when a new message arrives (on main thread via after())."""
        self._refresh_thread_list()
        # If this message belongs to the active thread, append it
        active = self._app.comms.active_thread
        if msg.thread_key == active:
            self._render_message(msg)

    def refresh_contacts(self) -> None:
        """Rebuild contacts and group listboxes from CommsManager state."""
        comms = self._app.comms

        # Contacts
        self._contacts_lb.delete(0, "end")
        for c in comms.contacts:
            self._contacts_lb.insert("end", c)

        # Groups
        self._groups_lb.delete(0, "end")
        for name, members in comms.groups.items():
            self._groups_lb.insert("end", f"{name}  ({len(members)} members)")

        # Rebuild To: combobox options
        options: list[str] = list(comms.contacts)
        for name in comms.groups:
            options.append(f"@{name}")
        self._to_combo["values"] = options

    def refresh_heard(self) -> None:
        """Rebuild heard-stations list."""
        self._heard_lb.delete(0, "end")
        for call in self._app.comms.heard:
            self._heard_lb.insert("end", call)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refresh_thread_list(self) -> None:
        """Rebuild thread listbox, marking unread counts."""
        comms = self._app.comms
        keys = comms.all_thread_keys()
        active = comms.active_thread
        self._threads_lb.delete(0, "end")
        for key in keys:
            unread = comms.unread_for_thread(key)
            label = key
            if unread:
                label = f"{key}  [{unread} new]"
            self._threads_lb.insert("end", label)
            if key == active:
                last_idx = self._threads_lb.size() - 1
                self._threads_lb.selection_set(last_idx)
                self._threads_lb.see(last_idx)

    # ------------------------------------------------------------------
    # Profile integration
    # ------------------------------------------------------------------

    def apply_profile(self, p) -> None:
        """Load profile values into comms tab widgets."""
        self._intro_note_var.set(getattr(p, "chat_intro_note", "uConsole HAM HAT online"))

    def collect_profile(self, p) -> None:
        """Write comms tab widget values back into profile object."""
        p.chat_intro_note = self._intro_note_var.get()
        # contacts/groups are serialized by CommsManager directly
