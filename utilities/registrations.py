"""
Various reverse-engineered versions of the allocation algorithms
used by different countries to allocate 24-bit ICAO addresses based
on the aircraft registration.

These were worked out by looking at the allocation patterns and
working backwards to an algorithm that generates that pattern,
spot-checking aircraft to see if it worked.
YMMV.
Translated to Python from: https://github.com/wiedehopf/tar1090/blob/master/html/registrations.js by WeegeeNumbuh1
"""
from math import floor
def registration_from_hexid(hexid_input: str) -> str | None:
    """
    Hex id needs to be a string. Returns a registration or None.
    """
    # input validation
    try:
        # convert to int
        if hexid_input.startswith("~"): return None
        hexid_input = int(hexid_input, 16)
    except:
        return None

    limited_alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ" # 24 chars; no I, O
    full_alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" # 26 chars

    """
    Handles 3-letter suffixes assigned with a regular pattern.
    start: first hexid of range
    s1: major stride (interval between different first letters)
    s2: minor stride (interval between different second letters)
    prefix: the registration prefix

    optionally:
    alphabet: the alphabet to use (defaults full_alphabet)
    first: the suffix to use at the start of the range (default: AAA)
    last: the last valid suffix in the range (default: ZZZ) """
    stride_mappings = [
        # South African stride mapping apparently no longer in use
        # { start: 0x008011, s1: 26*26, s2: 26, prefix: "ZS-" },

        {"start": 0x380000, "s1": 1024, "s2": 32, "prefix": "F-B" },
        {"start": 0x388000, "s1": 1024, "s2": 32, "prefix": "F-I" },
        {"start": 0x390000, "s1": 1024, "s2": 32, "prefix": "F-G" },
        {"start": 0x398000, "s1": 1024, "s2": 32, "prefix": "F-H" },
        {"start": 0x3A0000, "s1": 1024, "s2": 32, "prefix": "F-O" },
        {"start": 0x3C4421, "s1": 1024,  "s2": 32, "prefix": "D-A", "first": 'AAA', "last": 'OZZ' },
        {"start": 0x3C0001, "s1": 676, "s2": 26, "prefix": "D-A", "first": 'PAA', "last": 'ZZZ' },
        {"start": 0x3C8421, "s1": 1024,  "s2": 32, "prefix": "D-B", "first": 'AAA', "last": 'OZZ' },
        {"start": 0x3C2001, "s1": 676, "s2": 26, "prefix": "D-B", "first": 'PAA', "last": 'ZZZ' },
        {"start": 0x3CC000, "s1": 676, "s2": 26, "prefix": "D-C" },
        {"start": 0x3D04A8, "s1": 676, "s2": 26, "prefix": "D-E" },
        {"start": 0x3D4950, "s1": 676, "s2": 26, "prefix": "D-F" },
        {"start": 0x3D8DF8, "s1": 676, "s2": 26, "prefix": "D-G" },
        {"start": 0x3DD2A0, "s1": 676, "s2": 26, "prefix": "D-H" },
        {"start": 0x3E1748, "s1": 676, "s2": 26, "prefix": "D-I" },
        {"start": 0x448421, "s1": 1024,  "s2": 32, "prefix": "OO-" },
        {"start": 0x458421, "s1": 1024,  "s2": 32, "prefix": "OY-" },
        {"start": 0x460000, "s1": 676, "s2": 26, "prefix": "OH-" },
        {"start": 0x468421, "s1": 1024,  "s2": 32, "prefix": "SX-" },
        {"start": 0x490421, "s1": 1024,  "s2": 32, "prefix": "CS-" },
        {"start": 0x4A0421, "s1": 1024,  "s2": 32, "prefix": "YR-" },
        {"start": 0x4B8421, "s1": 1024,  "s2": 32, "prefix": "TC-" },
        {"start": 0x740421, "s1": 1024,  "s2": 32, "prefix": "JY-" },
        {"start": 0x760421, "s1": 1024,  "s2": 32, "prefix": "AP-" },
        {"start": 0x768421, "s1": 1024,  "s2": 32, "prefix": "9V-" },
        {"start": 0x778421, "s1": 1024,  "s2": 32, "prefix": "YK-" },
        {"start": 0xC00001, "s1": 676, "s2": 26, "prefix": "C-F" },
        {"start": 0xC044A9, "s1": 676, "s2": 26, "prefix": "C-G" },
        {"start": 0xE01041, "s1": 4096,  "s2": 64, "prefix": "LV-" }
    ]

    ''' numeric registrations
    start: start hexid in range
    first: first numeric registration
    count: number of numeric registrations
    template: registration template, trailing characters are replaced with the numeric registration '''
    numeric_mappings = [
        {"start": 0x140000, "first": 0,    "count": 100000, "template": "RA-00000" },
        {"start": 0x0B03E8, "first": 1000, "count": 1000,   "template": "CU-T0000" }
    ]
    
    # fill in some derived data
    for i in range(len(stride_mappings)):
        mapping = stride_mappings[i]

        if not 'alphabet' in mapping:
            mapping['alphabet'] = full_alphabet

        if 'first' in mapping:
            c1 = mapping['alphabet'].index(mapping['first'][0])
            c2 = mapping['alphabet'].index(mapping['first'][1])
            c3 = mapping['alphabet'].index(mapping['first'][2])
            mapping['offset'] = int(c1 * mapping['s1'] + c2 * mapping['s2'] + c3)
        else:
            mapping['offset'] = 0

        if 'last' in mapping:
            c1 = mapping['alphabet'].index(mapping['last'][0])
            c2 = mapping['alphabet'].index(mapping['last'][1])
            c3 = mapping['alphabet'].index(mapping['last'][2])
            mapping['end'] = mapping['start'] - mapping['offset'] +\
                c1 * mapping['s1'] +\
                c2 * mapping['s2'] +\
                c3
        else:
            mapping['end'] = mapping['start'] - mapping['offset'] +\
                (len(mapping['alphabet']) - 1) * mapping['s1'] +\
                (len(mapping['alphabet']) - 1) * mapping['s2'] +\
                (len(mapping['alphabet']) - 1)

    for i in range(len(numeric_mappings)):
        numeric_mappings[i]['end'] = numeric_mappings[i]['start'] + numeric_mappings[i]['count'] - 1


    def stride_reg(hexid) -> str | None:
        # try the mappings in stride_mappings
        for i in range(len(stride_mappings)):
            mapping = stride_mappings[i]
            if (hexid < mapping['start'] or hexid > mapping['end']):
                continue

            offset = hexid - mapping['start'] + mapping['offset']

            i1 = floor(offset / mapping['s1'])
            offset = offset % mapping['s1']
            i2 = floor(offset / mapping['s2'])
            offset = offset % mapping['s2']
            i3 = offset

            if (i1 < 0 or i1 >= len(mapping['alphabet']) or\
                i2 < 0 or i2 >= len(mapping['alphabet']) or\
                i3 < 0 or i3 >= len(mapping['alphabet'])):
                continue

            return mapping['prefix'] + mapping['alphabet'][i1] + mapping['alphabet'][i2] + mapping['alphabet'][i3]

        # nothing
        return None

    def numeric_reg(hexid) -> str | None:
        # try the mappings in numeric_mappings
        for i in range(len(numeric_mappings)):
            mapping = numeric_mappings[i]
            if (hexid < mapping['start'] or hexid > mapping['end']):
                continue

            reg = (hexid - mapping['start'] + mapping['first']) + ""
            return mapping['template'][:len(mapping['template'] - len(reg))] + reg

    # US N-numbers
    def n_letter(rem) -> str:
        if (rem == 0):
            return ""

        rem -= 1
        return limited_alphabet[rem]

    def n_letters(rem) -> str:
        if (rem == 0):
            return ""

        rem -= 1
        return limited_alphabet[floor(rem / 25)] + n_letter(rem % 25)

    def n_reg(hexid) -> str | None:
        offset = hexid - 0xA00001
        if (offset < 0 or offset >= 915399):
            return None

        digit1 = floor(offset / 101711) + 1
        reg = "N" + str(digit1)
        offset = offset % 101711
        if (offset <= 600):
            # Na, NaA .. NaZ, NaAA .. NaZZ
            return reg + n_letters(offset)

        # Na0* .. Na9*
        offset -= 601

        digit2 = floor(offset / 10111)
        reg = reg + str(digit2)
        offset = offset % 10111

        if (offset <= 600):
            # Nab, NabA..NabZ, NabAA..NabZZ
            return reg + n_letters(offset)

        # Nab0* .. Nab9*
        offset -= 601

        digit3 = floor(offset / 951)
        reg = reg + str(digit3)
        offset = offset % 951

        if (offset <= 600):
            # Nabc, NabcA .. NabcZ, NabcAA .. NabcZZ
            return reg + n_letters(offset)

        # Nabc0* .. Nabc9*
        offset -= 601

        digit4 = floor(offset / 35)
        reg = reg + str(round(digit4, 0))
        offset = offset % 35

        if (offset <= 24):
            # Nabcd, NabcdA .. NabcdZ
            return reg + n_letter(offset)

        # Nabcd0 .. Nabcd9
        offset -= 25
        return reg + str(round(offset, 0))

    # South Korea
    def hl_reg(hexid) -> str | None:
        if (hexid >= 0x71BA00 and hexid <= 0x71bf99):
            return "HL" + hex(hexid - 0x71BA00 + 0x7200)[2:]

        if (hexid >= 0x71C000 and hexid <= 0x71C099):
            return "HL" + hex(hexid - 0x71C000 + 0x8000)[2:]

        if (hexid >= 0x71C200 and hexid <= 0x71C299):
            return "HL" + hex(hexid - 0x71C200 + 0x8200)[2:]

        return None
 
    # Japan
    def ja_reg(hexid) -> str | None:
        offset = hexid - 0x840000
        if (offset < 0 or offset >= 229840):
            return None

        reg = "JA"

        digit1 = floor(offset / 22984)
        if (digit1 < 0 or digit1 > 9):
            return None
        reg = reg + str(digit1)
        offset = offset % 22984

        digit2 = floor(offset / 916)
        if (digit2 < 0 or digit2 > 9):
            return None
        reg = reg + str(digit2)
        offset = offset % 916

        if (offset < 340):
            # 3rd is a digit, 4th is a digit or letter
            digit3 = floor(offset / 34)
            reg = reg + str(digit3)
            offset = offset % 34

            if (offset < 10):
                # 4th is a digit
                return reg + str(offset)

            # 4th is a letter
            offset -= 10
            return reg + str(limited_alphabet[offset])

        # 3rd and 4th are letters
        offset -= 340
        letter3 = floor(offset / 24)
        return reg + limited_alphabet[letter3] + limited_alphabet[offset % 24]

    def lookup(hexid) -> str | None:
        #if hexid.isnumeric():
        #   return None

        reg = n_reg(hexid)
        if reg is not None:
            return reg

        reg = ja_reg(hexid)
        if reg is not None:
            return reg

        reg = hl_reg(hexid)
        if reg is not None:
            return reg

        reg = numeric_reg(hexid)
        if reg is not None:
            return reg

        reg = stride_reg(hexid)
        if reg is not None:
            return reg

        return None
    
    return lookup(hexid_input)
