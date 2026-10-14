"""Сумма прописью: «Сто сорок четыре тысячи восемьсот двадцать пять теңге 00 тиын»."""

_UNITS_M = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_UNITS_F = ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_TEENS = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать",
          "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят",
         "восемьдесят", "девяносто"]
_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот",
             "восемьсот", "девятьсот"]

# (формы для 1, 2-4, 5+), женский род
_SCALES = [
    (("", "", ""), False),
    (("тысяча", "тысячи", "тысяч"), True),
    (("миллион", "миллиона", "миллионов"), False),
    (("миллиард", "миллиарда", "миллиардов"), False),
]


def _plural(n: int, forms: tuple[str, str, str]) -> str:
    n = abs(n) % 100
    if 11 <= n <= 19:
        return forms[2]
    n %= 10
    if n == 1:
        return forms[0]
    if 2 <= n <= 4:
        return forms[1]
    return forms[2]


def _triad(n: int, feminine: bool) -> list[str]:
    words = [_HUNDREDS[n // 100]]
    rest = n % 100
    if 10 <= rest <= 19:
        words.append(_TEENS[rest - 10])
    else:
        words.append(_TENS[rest // 10])
        words.append((_UNITS_F if feminine else _UNITS_M)[rest % 10])
    return [w for w in words if w]


def int_to_words(n: int) -> str:
    if n == 0:
        return "ноль"
    parts = []
    for i, (forms, feminine) in enumerate(_SCALES):
        triad = (n // 1000 ** i) % 1000
        if triad == 0:
            continue
        chunk = _triad(triad, feminine)
        if i > 0:
            chunk.append(_plural(triad, forms))
        parts = chunk + parts
    return " ".join(parts)


def amount_in_words(amount: float, currency: str = "теңге", cents: str = "тиын") -> str:
    total_cents = round(amount * 100)
    whole, frac = divmod(total_cents, 100)
    text = f"{int_to_words(whole)} {currency} {frac:02d} {cents}"
    return text[0].upper() + text[1:]
