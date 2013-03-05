import webapp2, cgi, os, datetime, urllib, logging
import settings as bitsettings
from xml.etree import ElementTree
from google.appengine.api import users, mail
from google.appengine.ext import ndb
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext.webapp.mail_handlers import InboundMailHandler
from google.appengine.datastore.datastore_query import Cursor

## Load custom template filters 
register = template.register_template_library('tags.templatefilters')

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
        for name, uri in bitsettings.providers.items():
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
        listings_query = {}
        user = users.get_current_user()
        for cat in bitsettings.categories:
            listings_query[cat['ID']] = Post.query(Post.category==cat['ID']).order(-Post.engage).fetch(bitsettings.main_fetch)
        template_values = {
            'gvalues': get_global_template_vars(self, user, 10),
            'listings': listings_query,
            'categories': bitsettings.categories,
            'date': datetime.datetime.now(),
        }

        path = os.path.join( os.path.dirname(__file__), 'www/templates/main.html' )
        self.response.out.write( template.render( path, template_values ))

##
# Post, PostForm, and PostView form the basis of the listings side of the the application
# Post is the data model (below)
# PostForm is the create/update form
# PostView is the publically-available post
# DeletePost simply removes the indicated object from the datastore
##

class PostForm(webapp2.RequestHandler):
    def get(self):
        user = users.get_current_user()
        if user:
            template_values = {
                'gvalues': get_global_template_vars(self, user),
                'categories': bitsettings.categories,
                'subcategories': bitsettings.subcategories,
            }
            if self.request.get('postID'):
                this_post = ndb.Key( urlsafe = self.request.get('postID') ).get()
                if this_post.traderID == str(user.email()):
                    template_values["this_post"] = this_post

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
        if self.request.get('postID'):
            # if the post exists (i.e. we're editing rather than creating), get that post
            post = ndb.Key( urlsafe = self.request.get('postID') ).get()
        else:
            # otherwise, create a new post, and add all the immutable details to it
            post = Post()
            post.traderID = str(user.email())
        # These items can be edited post-creation, as the post page changes over time, 
        # this list should also change to include everything in the form
        post.title = self.request.get('title')
        post.location = self.request.get('location')
        post.price = "%.8f" % float(self.request.get('price'))
        post.content = self.request.get('content')
        post.category = self.request.get('category')
        post.subcategory = self.request.get('subcategory')

   
        if not post.postID:
            postID = post.put()
            post.postID = postID.urlsafe()
            post.contact = post.postID + "@" + bitsettings.email_suffix
        # This either adds the post.postID to the entity if there wasn't one, or updates the edited fields otherwise
        post.put()
        

        self.redirect('/post?' + urllib.urlencode( {'postID' : post.postID } ) )




class PostView(webapp2.RequestHandler):
    def get(self):
        try:
            listing = ndb.Key( urlsafe = self.request.get('postID') ).get()
        except:
            listing = []
        user = users.get_current_user()
        

        template_values = {
            'gvalues': get_global_template_vars(self, user),
            'listing': listing,
        }

        path = os.path.join( os.path.dirname(__file__), 'www/templates/post.html' )
        self.response.out.write( template.render( path, template_values ))
    
    def post(self):
        this_post = ndb.Key( urlsafe = self.request.get('postID') ).get()
        recipient_address = this_post.traderID
        user = users.get_current_user()
        template_values = {
            'gvalues': get_global_template_vars(self, user),
            'listing': this_post,
            'postID' : this_post.postID,
        }
        if not mail.is_email_valid(self.request.get("sender_email")):
            user = users.get_current_user()
            template_values['status_message'] = bitsettings.email_not_sent
        else:
            post_url = bitsettings.site_url + "/post?postID=" + this_post.postID
            
            ## get email from the email_text.xml file
            email = get_email_text("Post Reply")
            # compose the body of the message being sent
            full_message = mail.EmailMessage(sender     = "%s <admin@%s>" % (bitsettings.site_name, bitsettings.email_suffix) ,
                                             subject    = "Reply to '%s'" % (this_post.title) ,
                                             to         = "%s <%s>" % (this_post.traderID.split('@')[0], this_post.traderID) ,
                                             reply_to   = self.request.get("sender_email") ,
                                             body       = email.find('header').text
                                             + "\n" + post_url
                                             + "\n\n" + self.request.get("sender_message") 
                                             + "\n\n" + email.find('footer').text ,
            )
            full_message.send()
            template_values['status_message'] = bitsettings.email_sent
        path = os.path.join( os.path.dirname(__file__), 'www/templates/post_status.html' )
        self.response.out.write( template.render( path, template_values ))

class DeletePost(webapp2.RequestHandler):
    def get(self):
        user = users.get_current_user()
        postID = self.request.get('postID')
        if user and postID:
            post_key = ndb.Key( urlsafe = postID )
            this_post = post_key.get()
            if this_post.traderID == str(user.email()):
                post_key.delete()

        self.redirect('/trader')
        
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
            'user_id' : user.user_id(),
        }
            path = os.path.join( os.path.dirname(__file__), 'www/templates/trader.html' )
        else:
            template_values = {
            'gvalues': get_global_template_vars(self, user),
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
                'date' : datetime.datetime.now(),
            }

            path = os.path.join( os.path.dirname(__file__), 'www/templates/posts.html' )
        else:
            template_values = {
                'gvalues': get_global_template_vars(self),
            }
            path = os.path.join( os.path.dirname(__file__), 'www/templates/not_logged_in.html' )
        
        self.response.out.write( template.render( path, template_values ))

##
# Category View
#
##

class CategoryView(webapp2.RequestHandler):
    def get(self):
        user = users.get_current_user()
        if not self.request.get('category'):
            self.redirect('/')
        else:
            if self.request.get('subcategory'):
                listings = Post.query(Post.category==self.request.get('category'), Post.subcategory==self.request.get('subcategory')).order(-Post.engage).fetch(bitsettings.main_fetch)

            else:
                listings = Post.query(Post.category==self.request.get('category')).order(-Post.engage).fetch(bitsettings.main_fetch)

            template_values = {
            'gvalues': get_global_template_vars(self, user),
            'posts': listings,
            'date': datetime.datetime.now()
            }
            path = os.path.join( os.path.dirname(__file__), 'www/templates/posts.html' )
                

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
        this_post = Post.query(Post.contact==message.to).order(-Post.engage).get()
        email_to = this_post.traderID

        if mail.is_email_valid(email_to):
            email_messages = message.bodies('text/plain')
            email = get_email_text("Post Reply")
            
            for content_type, msg in email_messages:
                full_message = mail.EmailMessage(sender     = "%s <admin@%s>" % (bitsettings.site_name, bitsettings.email_suffix) ,
                                                 subject    = "Reply to '%s'" % (this_post.title) ,
                                                 to         = "%s <%s>" % (email_to.split('@')[0], email_to) ,
                                                 reply_to   = message.sender ,
                                                 body       = email.find('header').text 
                                                 + "\n\n" + str(message.subject).upper() 
                                                 + "\n" + msg.decode() 
                                                 + "\n\n" + email.find('footer').text ,
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
    price = ndb.StringProperty()
    content = ndb.TextProperty()
    engage = ndb.DateTimeProperty(auto_now_add=True)    # datetime of inital post
    edit = ndb.DateTimeProperty(auto_now=True)          # datetime of intial post & all edits
    contact = ndb.StringProperty()                      # public email attached to post
    category = ndb.StringProperty()
    subcategory = ndb.StringProperty()




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
                                ( '/post/edit/delete', DeletePost ),
                                ( '/trader'       , TraderView ),
                                ( '/trader/posts' , TraderPostView ),
                                ( '/category'     , CategoryView ),
                                ],
                            debug = True)

def main():
    run_wsgi_app(app)

if __name__ == '__main__':
    main()