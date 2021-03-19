
def find_key_case_insensitive(data, key, default=None):
    value = data.get(key)
    if value:
        return value

    '''
    Necessary to find keys where the first character
    is capitalized
    '''
    value = data.get(key[0].upper() + key[1:])
    if value:
        return value

    value = data.get(key.upper())
    if value:
        return value

    return default

def get_iddata(base, uuid, name, obdata):
    """
    This is taken from the import_3dm add-on:
    https://github.com/jesterKing/import_3dm
    # Copyright (c) 2018-2019 Nathan Letwory, Joel Putnam, 
    Tom Svilans

    Get an iddata. If an object with given uuid is found in
    this .blend use that. Otherwise new up one with base.new,
    potentially with obdata if that is set
    """
    founditem = None
    if uuid is not None:
        for item in base:
            if item.get('speckle_id', None) == str(uuid):
                founditem = item
                break
    elif name:
        for item in base:
            if item.get('name', None) == name:
                founditem = item
                break
    if founditem:
        theitem = founditem
        theitem['name'] = name
        if obdata:
            theitem.data = obdata
    else:
        if obdata:
            theitem = base.new(name=name, object_data=obdata)
        else:
            theitem = base.new(name=name)
        tag_data(theitem, uuid, name)
    return theitem