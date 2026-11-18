"""Pixel stickers: draws each sticker below as an SVG in library/stickers/ (pixel-<name>.svg).

Icon rules: 10 x 10 pixel grid, colours from the palette below only, at most four colours,
transparent, crisp edges, drawn at 12x. Add a sticker by adding a grid; then run:
python -I pixel_stickers.py
"""
import pathlib

OUT = pathlib.Path(__file__).resolve().parents[2] / "library" / "stickers"

COLOURS = {  # a plain palette; change it to your own colours
    "K": "#121212",  # ink
    "A": "#4FC3F7",  # light blue
    "W": "#FFFFFF",  # white
    "V": "#9575CD",  # purple
    "C": "#EF5350",  # red (make)
    "T": "#66BB6A",  # green (safe & progress)
    "Y": "#FFD54F",  # yellow (ideas)
    "M": "#F06292",  # pink (celebrate)
    "L": "#AED581",  # lime (only on screen colours)
    "N": "#2C2C2E",  # raised screen grey
    "S": "#1C1C1E",  # screen
}

STICKERS = {
    "idea": [  # lightbulb: tips, "did you know"
        "...KKKK...",
        "..KYYYYK..",
        ".KYWWYYYK.",
        ".KYWYYYYK.",
        ".KYYYYYYK.",
        "..KYYYYK..",
        "...KYYK...",
        "...KKKK...",
        "...KNNK...",
        "....KK....",
    ],
    "question": [  # open questions
        "..VVVVVV..",
        ".VVWVVVVV.",
        ".VV....VV.",
        "......VVV.",
        ".....VVV..",
        "....VVV...",
        "....VV....",
        "..........",
        "....VV....",
        "....VV....",
    ],
    "code": [  # programming: a terminal with a prompt
        "NNNNNNNNNN",
        "NANANNNNNN",
        "NSSSSSSSSN",
        "NSLSSSSSSN",
        "NSSLSSSSSN",
        "NSLSSAAASN",
        "NSSSSSSSSN",
        "NNNNNNNNNN",
    ],
    "no": [  # don't / wrong
        "CC......CC",
        "CCC....CCC",
        ".CCC..CCC.",
        "..CCCCCC..",
        "...CCCC...",
        "...CCCC...",
        "..CCCCCC..",
        ".CCC..CCC.",
        "CCC....CCC",
        "CC......CC",
    ],
    "yes": [  # right / on track
        "........TT",
        ".......TTT",
        "......TTT.",
        "TT...TTT..",
        "TTT.TTT...",
        ".TTTTT....",
        "..TTT.....",
        "...T......",
    ],
    "heart": [  # love it, like
        ".MM....MM.",
        "MMMM..MMMM",
        "MWMMMMMMMM",
        "MWMMMMMMMM",
        "MMMMMMMMMM",
        ".MMMMMMMM.",
        "..MMMMMM..",
        "...MMMM...",
        "....MM....",
    ],
    "star": [  # celebrate, key point
        "....YY....",
        "....YY....",
        "...YYYY...",
        "YYYYWYYYYY",
        ".YYYYYYYY.",
        "..YYYYYY..",
        "..YYYYYY..",
        ".YYY..YYY.",
        ".YY....YY.",
    ],
    "robot": [  # AI, robots
        "....KK....",
        "....CC....",
        ".CCCCCCCC.",
        ".CWWCCWWC.",
        ".CWKCCWKC.",
        "CCCCCCCCCC",
        ".CCKKKKCC.",
        ".CCCCCCCC.",
    ],
    "school": [  # school, graduation
        "....KK....",
        "..KKKKKK..",
        "KKKKKKKKKK",
        "..KKKKKKY.",
        "...KKKK.Y.",
        "...NNNN.Y.",
        "...NNNN.YY",
    ],
    "growth": [  # growing, getting better: rising bars
        "........TT",
        "........TT",
        ".....TT.TT",
        ".....TT.TT",
        "..TT.TT.TT",
        "..TT.TT.TT",
        "KKKKKKKKKK",
    ],
}


def svg(rows, name, scale=12):
    w, h = len(rows[0]), len(rows)
    assert all(len(r) == w for r in rows), name
    used = {ch for r in rows for ch in r if ch != "."}
    assert len(used) <= 4, f"{name}: {len(used)} colours (limit is 4)"
    rects = "".join(f'<rect x="{x}" y="{y}" width="1" height="1" fill="{COLOURS[ch]}"/>'
                    for y, r in enumerate(rows) for x, ch in enumerate(r) if ch != ".")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w * scale}" height="{h * scale}" '
            f'shape-rendering="crispEdges" role="img" aria-label="pixel sticker: {name}">{rects}</svg>\n')


if __name__ == "__main__":
    for name, rows in STICKERS.items():
        (OUT / f"pixel-{name}.svg").write_text(svg(rows, name))
    print(f"wrote {len(STICKERS)} stickers to {OUT}")
