from google.appengine.ext import webapp

register = webapp.template.create_template_register()

@register.filter(name='keyvalue')
def keyvalue(dict, key):    
    return dict[key]