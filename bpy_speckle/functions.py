from bpy_speckle.clients import speckle_clients

"""
Speckle functions
"""

unit_scale = {
    "meters": 1.0,
    "centimeters": 0.01,
    "millimeters": 0.001,
    "inches": 0.0254,
    "feet": 0.3048,
    "kilometers": 1000.0,
    "mm": 0.001,
    "cm": 0.01,
    "m": 1.0,
    "km": 1000.0,
    "in": 0.0254,
    "ft": 0.3048,
    "yd": 0.9144,
    "mi": 1609.340,
}

"""
Utility functions
"""


def _report(msg):
    """
    Function for printing messages to the console
    """
    print("SpeckleBlender: {}".format(msg))


def get_scale_length(units):
    if units.lower() in unit_scale.keys():
        return unit_scale[units]
    _report("Units <{}> are not supported.".format(units))
    return 1.0


"""
Client, user, and stream functions
"""


def _check_speckle_client_user_stream(scene):
    """
    Verify that there is a valid user and stream
    """
    speckle = scene.speckle

    user = (
        speckle.users[int(speckle.active_user)]
        if len(speckle.users) > int(speckle.active_user)
        else None
    )

    if user is None:
        print("No users loaded.")

    stream = (
        user.streams[user.active_stream]
        if len(user.streams) > user.active_stream
        else None
    )

    if stream is None:
        print("Account contains no streams.")

    return (user, stream)
