import webapp2, cgi, os, datetime, urllib, hashlib
from google.appengine.api import users
from google.appengine.ext import webapp, db
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app


##
# OpenID Providers
# This list allows you to enable or disable OpenID providers at will, by commenting or uncomenting the code
# More options are available at https://developers.google.com/appengine/articles/openid but these are the majors.
##
providers = {
    'Google'   : 'https://www.google.com/accounts/o8/id',
    'Yahoo'    : 'yahoo.com',
    #'MySpace'  : 'myspace.com',
    #'AOL'      : 'aol.com',
    #'MyOpenID' : 'myopenid.com'
}


def get_login_link_list(page_self, user):
    """Helper function to provide the proper login/logout links"""
    if user:
        link = {}
        link['url'] = users.create_logout_url(page_self.request.uri)
        link['name'] = 'Logout'
        link_list = [link]
    else:
        link_list = []
        for name, uri in providers.items():
            link = {}
            link['url'] = users.create_login_url(federated_identity=uri)
            link['name'] = name
            link_list.append(link)

    return link_list

def get_trader_posts(user):
    trader_post_query = db.GqlQuery("SELECT * "
                                 "FROM Post "
                                 "WHERE traderID = :1 "
                                 "ORDER BY engage DESC ",
                                 user.user_id() )
    return trader_post_query



##
# MainPage & Associated Categories
# The MainPage is to serve as basically just a listing of categories, and then maybe soem featured posts
# Other Category classes are to serve as drill-down tools, and may not even exist.
##

class MainPage(webapp2.RequestHandler):
    
    def get(self):
        user = users.get_current_user()

        listings_query = Post.all().order('-engage')       

        template_values = {
            'link_list': get_login_link_list(self, user),
            'listings': listings_query,
        }

        path = os.path.join( os.path.dirname(__file__), 'www/templates/main.html' )
        self.response.out.write( template.render( path, template_values ))

##
# Post, PostForm, and PostView form the basis of the listings side of the the application
# Post is the data model (below)
# PostForm is the create/update form
# PostView is the publically-available post
##

class PostForm(webapp2.RequestHandler):
    def get(self):
        user = users.get_current_user()

        if user:
            categories = [{ "name" : "Digital Goods"  , "ID" : "digital" },
                          { "name" : "Real-Life Items", "ID" : "ephemeral"}]
            template_values = {
                'link_list': get_login_link_list(self, user),
                'categories': categories,
                'if_user': True,
            }
            path = os.path.join( os.path.dirname(__file__), 'www/templates/post_form.html' )
            self.response.out.write( template.render( path, template_values ))
        else:
            template_values = {
                'link_list': get_login_link_list(self, user),
            }
            path = os.path.join( os.path.dirname(__file__), 'www/templates/not_logged_in.html' )
            self.response.out.write( template.render( path, template_values ))
        

    def post(self):
        postID = self.request.get('postID')
        post = Post(parent=post_key(postID))
        user = users.get_current_user()
        
        post.traderID = str(user.user_id())
        
        post.title = self.request.get('title')
        post.location = self.request.get('location')
        post.price = float(self.request.get('price'))
        post.content = self.request.get('content')

        post.category = self.request.get('category')
 
        contact = hashlib.md5()
        contact.update( str( datetime.datetime.now() ) + post.title )
        contact = contact.hexdigest()
        post.contact = contact + '@bitlist.appspot.com'
        post.postID = contact

        post.put()

        self.redirect('/post?' + urllib.urlencode( {'postID' : post.postID } ) )




class PostView(webapp2.RequestHandler):
    def get(self):
        postID = self.request.get('postID')

        listings = db.GqlQuery("SELECT * "
                                "FROM Post "
                                "WHERE postID = :1 "
                                "ORDER BY engage DESC ",
                                postID )

        user = users.get_current_user()
        

        template_values = {
            'link_list': get_login_link_list(self, user),
            'listings': listings,
            'postID' : postID,
        }

        path = os.path.join( os.path.dirname(__file__), 'www/templates/post.html' )
        self.response.out.write( template.render( path, template_values ))
    
    

##
# Trader, TraderView form the basis of the registered-user side of the application
# Trader is the data model (below)
# TraderView is the privately-available self-page for any registered user
# TraderPostView will be a paginated view of the Trader's listings.
##

class TraderView(webapp2.RequestHandler):
    def get(self):
        user = users.get_current_user()

        template_values = {
            'link_list' : get_login_link_list(self, user),
            'nickname' : user.nickname(),
            'email' : user.email(), 
            'user_id' : user.user_id(), 
            'user_fid' : user.federated_identity(), 
            'user_prov' : user.federated_provider(),
            'trader_posts': get_trader_posts(user),
        }

        if user:
            path = os.path.join( os.path.dirname(__file__), 'www/templates/trader.html' )
        else:
            path = os.path.join( os.path.dirname(__file__), 'www/templates/not_logged_in.html' )
        

        self.response.out.write( template.render( path, template_values ))


    def post(self):
        user = users.get_current_user()
        trader = Trader(parent=trader_key( user.user_id() ))
        
        trader.realEmail = self.request.get('email')
        trader.name = self.request.get('name')
        if user:
            if user.federated_identity():
                trader.traderID = user.user_id()
            else:
                trader.traderID = user.user_id()

        trader.put()

        self.redirect('/trader?' + urllib.urlencode( {'trader' : str(trader.Key) } ) )




##
# Data Models
#
##

class Post(db.Model):
    postID = db.StringProperty()
    traderID = db.StringProperty()
    title = db.StringProperty()
    location = db.StringProperty()
    price = db.FloatProperty()
    content = db.TextProperty()
    engage = db.DateTimeProperty(auto_now_add=True)
    contact = db.EmailProperty()
    category = db.StringProperty()

def post_key(postID=None):
    """ Construct a Datastore key for the Post from the postID. """
    return db.Key.from_path('Post', postID or 'does_not_exist')




##
# Other GAE requirements
# app defines the URIs for everything in this file, which is relative to the URL supplies in app.yaml
# The rest is just fluff to keep me sane.
##
app = webapp2.WSGIApplication([('/', MainPage),
                                ('/post', PostView),
                                ('/post/edit', PostForm),
                                ('/trader', TraderView)],
                            debug = True)

def main():
    run_wsgi_app(app)

if __name__ == '__main__':
    main()