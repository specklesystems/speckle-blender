from typing import List


def to_rgba(argb_int: int) -> List[float]:
    """Converts the int representation of a colour into a percent RGBA list"""
    alpha = ((argb_int >> 24) & 255) / 255
    red = ((argb_int >> 16) & 255) / 255
    green = ((argb_int >> 8) & 255) / 255
    blue = (argb_int & 255) / 255

    return (red, green, blue, alpha)


def to_argb_int(diffuse_colour) -> int:
    """Converts an RGBA array to an ARGB integer"""
    diffuse_colour = diffuse_colour[-1:] + diffuse_colour[0:3]
    print(diffuse_colour)
    diffuse_colour = [int(val * 255) for val in diffuse_colour]
    print(diffuse_colour)

    return int.from_bytes(diffuse_colour, byteorder="big", signed=True)
