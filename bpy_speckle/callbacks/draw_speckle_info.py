'''
Drawing callback to display active Speckle user
'''

import blf
import bpy

def draw_speckle_info(self, context):
    '''
    Draw active user info on the 3d viewport
    '''
    scn = bpy.context.scene
    if len(scn.speckle.users) > 0:
        user = scn.speckle.users[int(scn.speckle.active_user)]
        dpi = bpy.context.preferences.system.dpi

        blf.position(0, 100, 50, 0)
        blf.size(0, 20, dpi)
        blf.draw(0, "Active Speckle user: {} ({})".format(user.name, user.email))
        blf.position(0, 100, 20, 0)
        blf.size(0, 16, dpi)
        blf.draw(0, "Server: {}".format(user.server))