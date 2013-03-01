import webapp2, cgi, os, datetime, urllib, hashlib, logging
from xml.etree import ElementTree
from google.appengine.api import users, mail
from google.appengine.ext import ndb
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext.webapp.mail_handlers import InboundMailHandler
from google.appengine.datastore.datastore_query import Cursor

##
# Site Name/URL and Email Suffix
# These is used in a few places to construct strings required for the emails
# email_suffix is used as the final piece of the contact_email when a post is created
# site_url is used to construct URLs in the email text.
##
site_url = 'bitcoinlist.appspot.com'
email_suffix = 'bitcoinlist.appspotmail.com'
site_name = "Bitcoin List"
# If changed here, the name should also be changed in: 
# Site title in nav bar: nav.html   - <a class="brand">Bitcoin List</a>
# Site title in browser: base.html  - <title>Bitcoin List</title>
##  This is the email address that all emails will be sent from, it MUST be registered on GAE
app_email_address = "connor.collins@gmail.com"


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

##
# Helper Functions
# These functions would otherwise be repeated in multiple classes.
##

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

def get_trader_posts(user, fetch=3):
    if user:
        user_id = user.email()
        trader_post_query = Post.query(Post.traderID==user_id)
        if fetch:
            trader_post_query = trader_post_query.fetch(fetch)
        return trader_post_query
    else:
        return None


def get_global_template_vars(self, user=None, length=None):
    





    template_values = {
            'link_list': get_login_link_list(self, user),
            'trader_posts': get_trader_posts(user, length),
            }
    return template_values



def get_email_text(email_name):
    xml_path = os.path.join( os.path.dirname(__file__), 'xml/email_text.xml' )
    tree = ElementTree.parse(xml_path)
    root = tree.getroot()
    for email in root.findall('email'):
            if email.get('name') == email_name:
                return email
##
# MainPage & Associated Categories
# The MainPage is to serve as basically just a listing of categories, and then maybe soem featured posts
# Other Category classes are to serve as drill-down tools, and may not even exist.
##

class MainPage(webapp2.RequestHandler):
    
    def get(self):
        user = users.get_current_user()

        listings_query = Post.query().order(-Post.engage)     

        template_values = {
            'gvalues': get_global_template_vars(self, user, 10),
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
            categories = [{ "name" : "Looking to Work"  , "ID" : "employee" },
                          { "name" : "Looking to Hire"  , "ID" : "employer" },
                          { "name" : "Looking to Buy"   , "ID" : "buyer"    },
                          { "name" : "Looking to Sell"  , "ID" : "seller"   },
                          ]
            subcategories = [{ "name" : "Web Design"            , "ID" : "webdesign" },
                             { "name" : "Web Programming"       , "ID" : "webdev"    },
                             { "name" : "Graphic Design"        , "ID" : "graphics"  },
                             { "name" : "Hardware Design"       , "ID" : "hardware"  },
                             { "name" : "Security"              , "ID" : "security"  },
                             { "name" : "Misc. Scripts"         , "ID" : "scipts"    },
                             { "name" : "Information Design"    , "ID" : "infodesign"},
                             { "name" : "Game Development"      , "ID" : "gamedev"   },
                            ]
            template_values = {
                'gvalues': get_global_template_vars(self, user),
                'categories': categories,
                'subcategories': subcategories,
            }
            path = os.path.join( os.path.dirname(__file__), 'www/templates/post_form.html' )
            self.response.out.write( template.render( path, template_values ))
        else:
            template_values = {
                'gvalues': get_global_template_vars(self, user),
            }
            path = os.path.join( os.path.dirname(__file__), 'www/templates/not_logged_in.html' )
            self.response.out.write( template.render( path, template_values ))
        

    def post(self):
        user = users.get_current_user()
        post = Post()
        post.traderID = str(user.email())
        post.title = self.request.get('title')
        post.location = self.request.get('location')
        post.price = float(self.request.get('price'))
        post.content = self.request.get('content')
        post.category = self.request.get('category')
        post.subcategory = self.request.get('subcategory') or None
        contact = hashlib.md5()
        contact.update( str( datetime.datetime.now() ) + post.title + str(post.price) )
        contact = contact.hexdigest()
        post.contact = contact + "@" + email_suffix
        post.postID = ndb.Key(Post, contact).urlsafe()


        post.put()

        

        self.redirect('/post?' + urllib.urlencode( {'postID' : post.postID } ) )




class PostView(webapp2.RequestHandler):
    def get(self):
        postID = self.request.get('postID')

        listings = Post.query(Post.postID==postID).order(-Post.engage)

        user = users.get_current_user()
        

        template_values = {
            'gvalues': get_global_template_vars(self, user),
            'listings': listings,
            'postID' : postID,
        }

        path = os.path.join( os.path.dirname(__file__), 'www/templates/post.html' )
        self.response.out.write( template.render( path, template_values ))
    
    def post(self):
        postID = self.request.get('postID')
        this_post = Post.query(Post.postID==postID).order(-Post.engage).get()
        recipient_address = this_post.traderID

        if not mail.is_email_valid(self.request.get("sender_email")):
            user = users.get_current_user()
            template_values = {
                'gvalues': get_global_template_vars(self, user),
                'listings': [this_post],
                'postID' : postID,
                'status_message' : "Your message had errors and was not sent.  Please enter a valid email address.",
            }

            path = os.path.join( os.path.dirname(__file__), 'www/templates/post_status.html' )
            self.response.out.write( template.render( path, template_values ))
        else:
            sender_address = "%s ^%s^" % (self.request.get("sender_name"), self.request.get("sender_email"))
            sender_message = self.request.get("sender_message")
            message_subject = "Message from %s about: %s" % (site_name, this_post.title)

            post_url = site_url + "/post?postID=" + postID
            
            ## get email from the email_text.xml file
            email = get_email_text("Post Reply")
            message_prefix = email.find('header').text
            message_suffix = email.find('footer').text
            # compose the body of the message being sent
            full_message = message_subject + " - " + recipient_address + " - " +sender_address + " - " +message_prefix + " - " + sender_message + " - " + message_suffix
      
            mail.send_mail(app_email_address, recipient_address, message_subject, full_message)

            user = users.get_current_user()
            template_values = {
                'gvalues': get_global_template_vars(self, user),
                'listings': [this_post],
                'postID' : postID,
                'status_message' : "Your message has been successfully sent.",
            }

            path = os.path.join( os.path.dirname(__file__), 'www/templates/post_status.html' )
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

        if user:
            template_values = {
            'gvalues': get_global_template_vars(self, user),
            'nickname' : user.nickname(),
            'email' : user.email(), 
            'user_id' : user.user_id(), 
            'user_fid' : user.federated_identity(), 
            'user_prov' : user.federated_provider(),
        }
            path = os.path.join( os.path.dirname(__file__), 'www/templates/trader.html' )
        else:
            template_values = {
            'link_list' : get_login_link_list(self, user),
            }
            path = os.path.join( os.path.dirname(__file__), 'www/templates/not_logged_in.html' )
        

        self.response.out.write( template.render( path, template_values ))



class TraderPostView(webapp2.RequestHandler):
    def get(self):
        user = users.get_current_user()

        if user:
            user_id = user.email()

            cursor = Cursor(urlsafe=self.request.get('cursor'))
            posts, next_cursor, more = Post.query(Post.traderID==user_id).order(-Post.engage).fetch_page(10, start_cursor=cursor)
            if next_cursor != None:
                next_cursor = next_cursor.urlsafe()

            template_values = {
                'gvalues': get_global_template_vars(self, user),
                'posts' : posts,
                'next' : next_cursor,
                'more' : more,
            }

            path = os.path.join( os.path.dirname(__file__), 'www/templates/trader_posts.html' )
        else:
            template_values = {
                'gvalues': get_global_template_vars(self),
            }
            path = os.path.join( os.path.dirname(__file__), 'www/templates/not_logged_in.html' )
        
        self.response.out.write( template.render( path, template_values ))

##
# EmailReceived
# This receives an email as a HTTP POST from any address, reformates it, and
# forwards the message to the post's owner's real email address.
##
class EmailReceived(InboundMailHandler):
    def post(self):
        #logging.info("Received a message from: ", mail_message.sender)
        message = mail.InboundEmailMessage(self.request.body)
        ## Get the traderID from the post based on the email address and "forward" the email
        post_id = message.to.split('@')[0]
        this_post = Post.query(Post.postID==post_id).order(-Post.engage).get()
        email_to = this_post.traderID

        if mail.is_email_valid(email_to):
            email_messages = message.bodies('text/plain')
            email = get_email_text("Post Reply")
            
            for content_type, msg in email_messages:
                full_message = mail.EmailMessage(sender="%s <admin@%s>" % (site_name, email_suffix) ,
                                                 subject="Reply to '%s'" % (this_post.title) ,
                                                 to="%s <%s>" % (email_to.split('@')[0], email_to) ,
                                                 body=email.find('header').text + "\n" + msg.decode() + "\n" + email.find('footer').text ,
                )
                full_message.send()
        else:
            email_messages = message.bodies('text/plain')
            email = get_email_text("Post Reply")
            
            for content_type, msg in email_messages:
                full_message = mail.EmailMessage(sender="%s <admin@%s>" % (site_name, email_suffix) ,
                                                 subject="ERROR: Reply to '%s'" % (this_post.title) ,
                                                 to="connor.collins@gmail.com" ,
                                                 body=email.find('header').text + "\n" + msg.decode() + "\n" + email.find('footer').text + "\nEmailed to: " + email_to,
                )
                full_message.send()

##
# Data Models
#
##

class Post(ndb.Model):
    postID = ndb.StringProperty()                       # URL-safe NDB key
    traderID = ndb.StringProperty()                     # OpenID email of user who posted
    title = ndb.StringProperty()
    location = ndb.StringProperty()
    price = ndb.FloatProperty()
    content = ndb.TextProperty()
    engage = ndb.DateTimeProperty(auto_now_add=True)
    contact = ndb.StringProperty()
    category = ndb.StringProperty()
    subcategory = ndb.StringProperty()

def post_key(postID=None):
    """ Construct a Datastore key for the Post from the postID. """
   # return ndb.Key.from_path('Post', postID or 'does_not_exist')




##
# Other GAE requirements
# app defines the URIs for everything in this file, which is relative to the URL supplies in app.yaml
# mail handles mail receipts, and none of those classes should be in app as they are internal
##
email_handler = webapp2.WSGIApplication( [ EmailReceived.mapping() ],
                            debug = True)
app = webapp2.WSGIApplication( [( '/'             , MainPage ),
                                ( '/post'         , PostView ),
                                ( '/post/edit'    , PostForm ),
                                ( '/trader'       , TraderView ),
                                ( '/trader/posts' , TraderPostView ),
                                ],
                            debug = True)

def main():
    run_wsgi_app(app)

if __name__ == '__main__':
    main()