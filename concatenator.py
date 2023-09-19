# This HLA combines a stream of bytes into multi-byte messages.
# To detect the end of a message and the start of the next one, you can choose between timeouts or
# delimiter bytes (or both).
# Output can be displayed as HEX or ASCII.
# Supported input protocols are I2C, SPI and Serial UART.

# This HLA was forked from Mark Garrison's example HLA "Text Messages"

# Settings constants.
from saleae.analyzers import HighLevelAnalyzer, AnalyzerFrame, StringSetting, NumberSetting, ChoicesSetting
from saleae.data import GraphTimeDelta

MESSAGE_PREFIX_SETTING = 'Message Prefix (optional)'
PACKET_TIMEOUT_SETTING = 'Packet Timeout [µs]'
PACKET_DELIMITER_SETTING = 'Packet Delimiter'
DISPLAY_FORMAT_SETTING = 'Display Format'

DELIMITER_CHOICES = {
    'None': '',
    'New Line [\\n]': '\n',
    'Null [\\0]': '\0',
    'Space [\' \']': ' ',
    'Semicolon [;]': ';',
    'Tab [\\t]': '\t'
}

DISPLAY_FORMAT_CHOICES = {
    'ASCII': 'ascii',
    'HEX': 'hex'
}

class Concatenator(HighLevelAnalyzer):

    temp_frame = None
    delimiter = '\n'

    # Settings:
    prefix = StringSetting(label='Message Prefix (optional)')
    packet_timeout = NumberSetting(label='Packet Timeout [µs]', min_value=1, max_value=1E10) # , default_value=30)
    delimiter_setting = ChoicesSetting(label='Packet Delimiter', choices=DELIMITER_CHOICES.keys())
    display_format_setting = ChoicesSetting(label='Display Format', choices=DISPLAY_FORMAT_CHOICES.keys())

    # Base output formatting options:
    result_types = {
        'error': {
            'format': 'Error!'
        },
    }

    def __init__(self):
        self.delimiter = DELIMITER_CHOICES.get(self.delimiter_setting, '\n')
        self.display_format = DISPLAY_FORMAT_CHOICES.get(self.display_format_setting, 'hex')
        self.result_types["message"] = {
            'format': self.prefix + '{{{data.formatted}}}'
        }

    def clear_stored_message(self, frame):
        self.temp_frame = AnalyzerFrame('message', frame.start_time, frame.end_time, {
            'address': '',
            'str': '',
            'hex': '',
            'mosi_str': '',
            'mosi_hex': '',
            'miso_str': '',
            'miso_hex': '',
        })

    def append(self, dataType, char, hexVal, mosiChar, mosiHexVal, misoChar, misoHexVal):
        if dataType == "onedir":
            self.temp_frame.data["str"] += char
            self.temp_frame.data["hex"] += hexVal + " "
        if dataType == "spi":
            self.temp_frame.data["mosi_str"] += mosiChar
            self.temp_frame.data["mosi_hex"] += mosiHexVal + " "
            self.temp_frame.data["miso_str"] += misoChar
            self.temp_frame.data["miso_hex"] += misoHexVal + " "

    def remove_empty_fields(self, frame):
        frame.data = dict(filter(lambda el: el[1] != '', frame.data.items()))
        return frame

    def format_bar_text(self, frame):
        frame.data["formatted"] = ''
        if self.display_format == 'hex':
            if frame.data['address'] != '':
                frame.data["formatted"] += 'address: ' + frame.data["address"] + "; "
            if frame.data['hex'] != '':
                frame.data["formatted"] += frame.data["hex"]
            if frame.data['mosi_hex'] != '' or frame.data['miso_hex'] != '':
                frame.data["formatted"] += 'MOSI: ' + frame.data['mosi_hex'] + ' MISO: ' + frame.data['miso_hex']
        if self.display_format != 'hex':
            if frame.data['address'] != '':
                frame.data["formatted"] += 'address: ' + frame.data["address"] + "; "
            if frame.data['str'] != '':
                frame.data["formatted"] += frame.data["str"]
            if frame.data['mosi_str'] != '' or frame.data['miso_str'] != '':
                frame.data["formatted"] += 'MOSI: ' + frame.data['mosi_str'] + ' MISO: ' + frame.data['miso_str']
        return frame

    def have_existing_message(self):
        if self.temp_frame is None:
            return False
        if len(self.temp_frame.data["str"]) == 0:
            return False
        return True

    def update_end_time(self, frame):
        self.temp_frame.end_time = frame.end_time

    def decode(self, frame: AnalyzerFrame):
        # This class method is called once for each frame produced by the input analyzer.
        # the "data" dictionary contents is specific to the input analyzer type. The readme with this repo contains a description of the "data" contents for each input analyzer type.
        # all frames contain some common keys: start_time, end_time, and type.

        # This function can either return nothing, a single new frame, or an array of new frames.
        # all new frames produced are dictionaries and need to have the required keys: start_time, end_time, and type
        # in addition, protocol-specific information should be stored in the "data" key, so that they can be accessed by rendering (using the format strings), by export, by the terminal view, and by the protocol search results list.
        # Not all of these are implemented yet, but we're working on it!

        # All protocols - use the delimiter specified in the settings.
        delimiters = [] if self.delimiter == '' else [self.delimiter]

        # All protocols - delimit on a delay specified in the settings
        # consider frames further apart than this separate messages
        maximum_delay = GraphTimeDelta(second=self.packet_timeout * 0.000001 or 0.5E-3)
        # I2C - delimit on address byte
        # SPI - delimit on Enable toggle. TODO: add support for the SPI analyzer to send Enable/disable frames, or at least a Packet ID to the low level analyzer.

        dataType = "none"
        char = "unknown error"
        hexVal = "unknown error"
        mosiChar = "unknown error"
        mosiHexVal = "unknown error"
        misoChar = "unknown error"
        misoHexVal = "unknown error"

        # setup initial result, if not present
        first_frame = False
        if self.temp_frame is None:
            first_frame = True
            self.clear_stored_message(frame)

        # handle serial data and I2C data
        if frame.type == "data" and "data" in frame.data.keys():
            dataType = "onedir"
            value = frame.data["data"][0]
            char = chr(value)
            hexVal = format(value, '02X')

        # handle I2C address
        if frame.type == "address":
            value = frame.data["address"][0]
            # if we have an existing message, send it
            if self.have_existing_message() == True:
                ret = self.temp_frame
                self.clear_stored_message(frame)
                self.temp_frame.data["address"] = hex(value)
                ret = self.format_bar_text(ret)
                ret = self.remove_empty_fields(ret)
                return ret
            # append the address to the beginning of the new message
            self.temp_frame.data["address"] = hex(value)
            return None

        # handle I2C start condition
        if frame.type == "start":
            return

        # handle I2C stop condition
        if frame.type == "stop":
            if self.have_existing_message() == True:
                ret = self.temp_frame
                self.temp_frame = None
                ret = self.format_bar_text(ret)
                ret = self.remove_empty_fields(ret)
                return ret
            self.temp_frame = None
            return

        # handle SPI byte
        if frame.type == "result":
            dataType = "spi"
            mosiChar = ""
            mosiHexVal = ""
            misoChar = ""
            misoHexVal = ""
            if "miso" in frame.data.keys():
                misoChar += chr(frame.data["miso"][0])
                misoHexVal += format(frame.data["miso"][0], '02X')
            if "mosi" in frame.data.keys():
                mosiChar += chr(frame.data["mosi"][0])
                mosiHexVal += format(frame.data["mosi"][0], '02X')

        # If we have a timeout event, commit the frame and make sure not to add the new frame after the delay, and add the current character to the next frame.
        if first_frame == False and self.temp_frame is not None:
            if self.temp_frame.end_time + maximum_delay < frame.start_time:
                ret = self.temp_frame
                self.clear_stored_message(frame)
                self.append(dataType, char, hexVal, mosiChar, mosiHexVal, misoChar, misoHexVal)
                ret = self.format_bar_text(ret)
                ret = self.remove_empty_fields(ret)
                return ret

        self.append(dataType, char, hexVal, mosiChar, mosiHexVal, misoChar, misoHexVal)
        self.update_end_time(frame)

        # if the current character is a delimiter, commit it.
        if (delimiters != []) and (char in delimiters):
            ret = self.temp_frame
            # leave the temp_frame blank, so the next frame is the beginning of the next message.
            self.temp_frame = None
            ret = self.format_bar_text(ret)
            ret = self.remove_empty_fields(ret)
            return ret
