import definitions
import mido
import push2_python
import time
import math
import json
import os

from pythonosc.udp_client import SimpleUDPClient
from definitions import PyshaMode, OFF_BTN_COLOR
from display_utils import show_text
import osc_utils


class MenuControl(object):

    color = definitions.GRAY_LIGHT
    color_rgb = None
    name = "Unknown"
    section = "unknown"
    address = "/default"
    min = 0.0
    max = 1.0
    value = 64
    vmin = 0
    vmax = 127
    get_color_func = None
    value_labels_map = {}

    def __init__(
        self, address, name, min, max, section_name, get_color_func, send_osc_func=None
    ):
        self.address = address
        self.name = name
        self.section = section_name
        self.get_color_func = get_color_func
        self.send_osc_func = send_osc_func
        self.min = min
        self.max = max

    def draw(self, ctx, x_part):
        margin_top = 25

        # Param name
        name_height = 20
        show_text(
            ctx,
            x_part,
            margin_top,
            self.name,
            height=name_height,
            font_color=definitions.WHITE,
        )

        # Param value
        val_height = 30
        color = self.get_color_func()
        show_text(
            ctx,
            x_part,
            margin_top + name_height,
            self.value_labels_map.get(str(self.value), str(self.value)),
            height=val_height,
            font_color=color,
        )

        # Knob
        ctx.save()

        circle_break_degrees = 80
        height = 55
        radius = height / 2

        display_w = push2_python.constants.DISPLAY_LINE_PIXELS
        x = (display_w // 8) * x_part
        y = margin_top + name_height + val_height + radius + 5

        start_rad = (90 + circle_break_degrees // 2) * (math.pi / 180)
        end_rad = (90 - circle_break_degrees // 2) * (math.pi / 180)
        xc = x + radius + 3
        yc = y

        def get_rad_for_value(value):
            total_degrees = 360 - circle_break_degrees
            return start_rad + total_degrees * (
                (value - self.vmin) / (self.vmax - self.vmin)
            ) * (math.pi / 180)

        # This is needed to prevent showing line from previous position
        ctx.set_source_rgb(0, 0, 0)
        ctx.move_to(xc, yc)
        ctx.stroke()

        # Inner circle
        ctx.arc(xc, yc, radius, start_rad, end_rad)
        ctx.set_source_rgb(*definitions.get_color_rgb_float(definitions.GRAY_LIGHT))
        ctx.set_line_width(1)
        ctx.stroke()

        # Outer circle
        ctx.arc(xc, yc, radius, start_rad, get_rad_for_value(self.value))
        ctx.set_source_rgb(*definitions.get_color_rgb_float(color))
        ctx.set_line_width(3)
        ctx.stroke()

        ctx.restore()

    def update_value(self, increment):
        if self.value + increment > self.vmax:
            self.value = self.vmax
        elif self.value + increment < self.vmin:
            self.value = self.vmin
        else:
            self.value += increment
        # print("update value: adress", self.address, "value", self.value)
        # Send cc message, subtract 1 to number because MIDO works from 0 - 127
        # msg = mido.Message('control_change', control=self.address, value=self.value)
        # msg=f'control_change {self.address} {self.value}'
        # print(self.address, osc_utils.scale_knob_value([self.value, self.min, self.max]))
        self.send_osc_func(
            self.address, osc_utils.scale_knob_value([self.value, self.min, self.max])
        )


class ClipMenuMode(PyshaMode):

    osc_address_button_names = [
        push2_python.constants.BUTTON_UPPER_ROW_1,
        push2_python.constants.BUTTON_UPPER_ROW_2,
        push2_python.constants.BUTTON_UPPER_ROW_3,
        push2_python.constants.BUTTON_UPPER_ROW_4,
        push2_python.constants.BUTTON_UPPER_ROW_5,
        push2_python.constants.BUTTON_UPPER_ROW_6,
        push2_python.constants.BUTTON_UPPER_ROW_7,
        push2_python.constants.BUTTON_UPPER_ROW_8,
    ]
    instrument_devices = {}
    active_osc_addresses = []
    current_selected_section_and_page = {}
    osc_port = None

    def initialize(self, settings=None):

        for (
            instrument_short_name
        ) in self.get_all_distinct_instrument_short_names_helper():
            try:
                inst = json.load(
                    open(
                        os.path.join(
                            definitions.INSTRUMENT_DEFINITION_FOLDER,
                            "{}.json".format(instrument_short_name),
                        )
                    )
                )
            except FileNotFoundError:
                inst = {}

            # osc = inst.get('osc', None)
            clip = inst.get("clip", None)
            osc_port = inst.get("osc_in_port", None)

            if osc_port:
                self.app.osc_clients[instrument_short_name] = SimpleUDPClient(
                    "127.0.0.1", osc_port
                )

            if clip is not None:
                # Create OSC mappings for instruments with definitions
                self.instrument_devices[instrument_short_name] = []
                for section in clip:
                    section_name = section["section"]

                    for name, address, min, max in section["controls"]:
                        control = MenuControl(
                            address,
                            name,
                            min,
                            max,
                            section_name,
                            self.get_current_track_color_helper,
                            self.app.send_osc,
                        )
                        if section.get("control_value_label_maps", {}).get(name, False):
                            control.value_labels_map = section[
                                "control_value_label_maps"
                            ][name]

                        self.instrument_devices[instrument_short_name].append(control)

                print(
                    "Loaded {0} OSC address mappings for instrument {1}".format(
                        len(self.instrument_devices[instrument_short_name]),
                        instrument_short_name,
                    )
                )
            else:
                # No definition file for instrument exists, or no midi CC were defined for that instrument
                self.instrument_devices[instrument_short_name] = []
                for i in range(0, 128):
                    section_s = (i // 16) * 16
                    section_e = section_s + 15
                    control = MenuControl(
                        i,
                        "CC {0}".format(i),
                        0.0,
                        1.0,
                        "{0} to {1}".format(section_s, section_e),
                        self.get_current_track_color_helper,
                        self.app.send_osc,
                    )
                    self.instrument_devices[instrument_short_name].append(control)
                print(
                    "Loaded default OSC address mappings for instrument {0}".format(
                        instrument_short_name
                    )
                )

        # Fill in current page and section variables
        for instrument_short_name in self.instrument_devices:
            self.current_selected_section_and_page[instrument_short_name] = (
                self.instrument_devices[instrument_short_name][0].section,
                0,
            )

    def get_all_distinct_instrument_short_names_helper(self):
        return self.app.track_selection_mode.get_all_distinct_instrument_short_names()

    def get_current_track_color_helper(self):
        return self.app.track_selection_mode.get_current_track_color()

    def get_current_track_instrument_short_name_helper(self):
        return self.app.track_selection_mode.get_current_track_instrument_short_name()

    def get_current_track_osc_address_sections(self):
        section_names = []
        for control in self.instrument_devices.get(
            self.get_current_track_instrument_short_name_helper(), []
        ):
            section_name = control.section
            if section_name not in section_names:
                section_names.append(section_name)
        return section_names

    def get_currently_selected_osc_address_section_and_page(self):
        return self.current_selected_section_and_page[
            self.get_current_track_instrument_short_name_helper()
        ]

    def get_osc_address_controls_for_current_track_and_section(self):
        section, _ = self.get_currently_selected_osc_address_section_and_page()
        return [
            control
            for control in self.instrument_devices.get(
                self.get_current_track_instrument_short_name_helper(), []
            )
            if control.section == section
        ]

    def get_osc_address_controls_for_current_track_section_and_page(self):
        all_section_controls = (
            self.get_osc_address_controls_for_current_track_and_section()
        )
        # print(all_section_controls)
        _, page = self.get_currently_selected_osc_address_section_and_page()
        try:
            return all_section_controls[page * 8 : (page + 1) * 8]
        except IndexError:
            return []

    def update_current_section_page(self, new_section=None, new_page=None):
        current_section, current_page = (
            self.get_currently_selected_osc_address_section_and_page()
        )
        result = [current_section, current_page]
        if new_section is not None:
            result[0] = new_section
        if new_page is not None:
            result[1] = new_page
        self.current_selected_section_and_page[
            self.get_current_track_instrument_short_name_helper()
        ] = result
        self.active_osc_addresses = (
            self.get_osc_address_controls_for_current_track_section_and_page()
        )
        self.app.buttons_need_update = True

    def get_should_show_osc_address_next_prev_pages_for_section(self):
        all_section_controls = (
            self.get_osc_address_controls_for_current_track_and_section()
        )
        _, page = self.get_currently_selected_osc_address_section_and_page()
        show_prev = False
        if page > 0:
            show_prev = True
        show_next = False
        if (page + 1) * 8 < len(all_section_controls):
            show_next = True
        return show_prev, show_next

    def new_instrument_selected(self):
        self.active_osc_addresses = (
            self.get_osc_address_controls_for_current_track_section_and_page()
        )

    def activate(self):
        self.update_buttons()

    def deactivate(self):
        for button_name in self.osc_address_button_names + [
            push2_python.constants.BUTTON_PAGE_LEFT,
            push2_python.constants.BUTTON_PAGE_RIGHT,
        ]:
            self.push.buttons.set_button_color(button_name, definitions.BLACK)

    def update_buttons(self):

        n_osc_address_sections = len(self.get_current_track_osc_address_sections())
        for count, name in enumerate(self.osc_address_button_names):
            if count < n_osc_address_sections:
                self.push.buttons.set_button_color(name, definitions.WHITE)
            else:
                self.push.buttons.set_button_color(name, definitions.BLACK)

        show_prev, show_next = (
            self.get_should_show_osc_address_next_prev_pages_for_section()
        )
        if show_prev:
            self.push.buttons.set_button_color(
                push2_python.constants.BUTTON_PAGE_LEFT, definitions.WHITE
            )
        else:
            self.push.buttons.set_button_color(
                push2_python.constants.BUTTON_PAGE_LEFT, definitions.BLACK
            )
        if show_next:
            self.push.buttons.set_button_color(
                push2_python.constants.BUTTON_PAGE_RIGHT, definitions.WHITE
            )
        else:
            self.push.buttons.set_button_color(
                push2_python.constants.BUTTON_PAGE_RIGHT, definitions.BLACK
            )

    def update_display(self, ctx, w, h):

        if not self.app.is_mode_active(self.app.settings_mode):
            # If settings mode is active, don't draw the upper parts of the screen because settings page will
            # "cover them"

            # Draw MIDI CCs section names
            section_names = self.get_current_track_osc_address_sections()[0:8]
            if section_names:
                height = 20
                for i, section_name in enumerate(section_names):
                    show_text(ctx, i, 0, section_name, background_color=definitions.RED)

                    is_selected = False
                    selected_section, _ = (
                        self.get_currently_selected_osc_address_section_and_page()
                    )
                    if selected_section == section_name:
                        is_selected = True

                    current_track_color = self.get_current_track_color_helper()
                    if is_selected:
                        background_color = current_track_color
                        font_color = definitions.BLACK
                    else:
                        background_color = definitions.BLACK
                        font_color = current_track_color
                    show_text(
                        ctx,
                        i,
                        0,
                        section_name,
                        height=height,
                        font_color=font_color,
                        background_color=background_color,
                    )

            # Draw MIDI CC controls
            if self.active_osc_addresses:
                for i in range(0, min(len(self.active_osc_addresses), 8)):
                    try:
                        self.active_osc_addresses[i].draw(ctx, i)
                    except IndexError:
                        continue

    def on_button_pressed(self, button_name):
        print(self.get_currently_selected_osc_address_section_and_page(), "sel section")
        if button_name in self.osc_address_button_names:
            current_track_sections = self.get_current_track_osc_address_sections()
            n_sections = len(current_track_sections)
            idx = self.osc_address_button_names.index(button_name)
            if idx < n_sections:
                new_section = current_track_sections[idx]
                self.update_current_section_page(new_section=new_section, new_page=0)
            return True

        elif button_name in [
            push2_python.constants.BUTTON_PAGE_LEFT,
            push2_python.constants.BUTTON_PAGE_RIGHT,
        ]:
            show_prev, show_next = (
                self.get_should_show_osc_address_next_prev_pages_for_section()
            )
            _, current_page = self.get_currently_selected_osc_address_section_and_page()
            if button_name == push2_python.constants.BUTTON_PAGE_LEFT and show_prev:
                self.update_current_section_page(new_page=current_page - 1)
            elif button_name == push2_python.constants.BUTTON_PAGE_RIGHT and show_next:
                self.update_current_section_page(new_page=current_page + 1)
            return True

    def on_encoder_rotated(self, encoder_name, increment):

        try:
            encoder_num = [
                push2_python.constants.ENCODER_TRACK1_ENCODER,
                push2_python.constants.ENCODER_TRACK2_ENCODER,
                push2_python.constants.ENCODER_TRACK3_ENCODER,
                push2_python.constants.ENCODER_TRACK4_ENCODER,
                push2_python.constants.ENCODER_TRACK5_ENCODER,
                push2_python.constants.ENCODER_TRACK6_ENCODER,
                push2_python.constants.ENCODER_TRACK7_ENCODER,
                push2_python.constants.ENCODER_TRACK8_ENCODER,
            ].index(encoder_name)
            if self.active_osc_addresses:
                self.active_osc_addresses[encoder_num].update_value(increment)
        except ValueError:
            pass  # Encoder not in list
        return True  # Always return True because encoder should not be used in any other mode if this is first active