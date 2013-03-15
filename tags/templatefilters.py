from google.appengine.ext import webapp

register = webapp.template.create_template_register()

@register.filter(name='keyvalue')
def keyvalue(dict, key):    
    return dict[key]

@register.filter(name='cat_name')
def cat_name(list, key):
    """ This filter translates the tag ID into the tag Name """
    for dict in list:
        if key == dict['ID']:
            return dict['name']
    return None