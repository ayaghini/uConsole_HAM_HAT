# Comms Tab (`CommsTab`)

## Left Panel: Contacts, Groups, Heard, Intro

| Element | Type | Connected code | What it actually does | Purpose and how to use |
|---|---|---|---|---|
| Contacts list | Listbox | `refresh_contacts()` from `CommsManager.contacts` | Displays saved direct-message contacts (uppercase normalized). | Select/read contact list for quick comms addressing. |
| Add... | Button | `_add_contact()` -> `HamHatApp.add_contact()` | Prompts callsign and adds contact if valid/new. | Add frequent direct peers. |
| Remove | Button | `_remove_contact()` -> `remove_contact()` | Removes selected contact after confirmation dialog. | Clean outdated contacts. |
| <- Heard | Button | `_import_heard_to_contacts()` | Imports all heard stations into contacts list. | Bootstrap contacts from live traffic. |
| Groups list | Listbox | `refresh_contacts()` from `CommsManager.groups` | Shows groups with member counts. | Manage/select group threads. |
| New... | Button | `_new_group()` -> `set_group()` | Prompts for group name + comma-separated members, then stores group. | Create broadcast/multi-station groups. |
| Edit... | Button | `_edit_group()` -> `set_group()` | Edits selected group member list. | Maintain current group membership. |
| Delete | Button | `_delete_group()` -> `delete_group()` | Deletes selected group after confirmation. | Remove obsolete groups. |
| Group members text | Label | `_on_group_select()` | Displays selected group member list summary. | Quick verification of group composition. |
| Heard Stations list | Listbox | `refresh_heard()` from `CommsManager.heard` | Shows unique heard calls discovered from received packets. | Track active stations on air. |
| Clear Heard | Button | `_clear_heard()` -> `clear_heard()` | Clears heard list immediately. | Reset heard list between sessions/tests. |
| Intro note | Entry | `_intro_note_var` | Text payload used by intro/discovery packet send. | Set short station discovery message. |
| Send Intro Packet | Button | `_send_intro()` -> `HamHatApp.send_intro()` | Sends intro wire payload containing source/lat/lon/note via APRS TX path. | Announce station presence/location to peers. |

## Right Panel: Threads, Messages, Compose

| Element | Type | Connected code | What it actually does | Purpose and how to use |
|---|---|---|---|---|
| Threads list | Listbox | `_refresh_thread_list()`, `_on_thread_select()` | Shows available thread keys and unread counts; selection sets active thread and clears its unread counter. | Navigate conversations efficiently. |
| Messages log | `BoundedLog` with tags | `_load_thread()`, `_render_message()`, `on_message()` | Displays TX/RX/SYS messages with color-coded prefixes. | Read conversation history for selected thread. |
| To | Combobox (editable) | `_to_var`; options rebuilt in `refresh_contacts()` | Accepts direct callsign or `@GROUP` target for outbound message routing. | Pick target quickly or type custom callsign/group. |
| Text | Multi-line `Text` | `_compose_text`; Enter handler `_on_compose_enter()` | Message composition box; Enter sends, Shift+Enter inserts newline. | Type message body then send. |
| Reliable | Checkbutton | `_reliable_var` | For direct messages, passes `reliable=True` to direct send path (ACK/retry). Ignored for `@group` send path. | Enable for important direct traffic needing delivery confirmation. |
| Send | Button | `_send_message()` | Sends direct (`send_direct_message`) or group (`send_group_message`) based on `To` format, then clears composer. | Main chat send action. |

## Behavioral Notes

| Component | Actual behavior |
|---|---|
| Incoming message routing | Thread key inferred from packet source/destination/group format; unread increments when RX hits non-active thread. |
| Thread auto-fill | Selecting a thread auto-populates `To` with callsign or `@GroupName`. |
| Intro dedup | Intro packets are deduplicated by source+lat+lon+note before creating chat/system effects. |
