import webapp2, os, datetime, urllib, operator, logging
import settings as bitsettings
from xml.etree import ElementTree
from google.appengine.api import users, mail, search
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
def get_category_list():
    """Returns a list of the categories and subcategory combinations that currently have posts."""
    category_list = []
    for category in bitsettings.categories:
        category_list.append( { 'nav': category['ID'], 
                                'category': category['name'], 
                                'subcategory_list' : set( 
                                    [  query_result.subcategory for query_result in Post.query( Post.category == category['ID'] )  ]    
                                ) } )

    return category_list


def get_login_link_list(page_self, user):
    """Helper function to provide the proper login/logout links.
    Use like get_login_link_list(self, user).
    This is taken care of via get_global_template_vars.
    """
    if user:
        # if there's a user we just need the logout link
        link = {}
        link['url'] = users.create_logout_url(page_self.request.uri)
        link['name'] = 'Logout'
        link_list = [link]
    else:
        # otherwise generate a list of all the providers and their links.
        link_list = []
        for name, uri in bitsettings.providers.items():
            link = {}
            link['url'] = users.create_login_url(federated_identity=uri)
            link['name'] = name
            link_list.append(link)

    return link_list

def get_trader_posts(user, fetch=bitsettings.trader_fetch):
    """Retrieves a list of the most recent posts made by the current user.
    Use like get_trader_posts(user[, fetch]) where fetch is the number of posts to return.
    Fetch defaults to bitsettings.trader_fetch.
    This is taken care of via get_global_template_vars.
    """
    if user:
        trader_post_query = Post.query( Post.traderID == user.email() ).fetch(fetch)
        return trader_post_query
    else:
        # if there's no user, there's no recent posts
        return None


def get_global_template_vars(self, user=None, fetch=None):
    """Gets the global variable values for use in the templates.
    Use like get_global_template_vars(self[, user[, fetch]],
    where the user and fetch both default to None (though fetch=None becomes fetch=bitsettings.trader_fetch),
    and fetch is the number of recent posts by the user to return in trader_posts.
    """
    template_values = {
            'link_list': get_login_link_list(self, user),
            'trader_posts': get_trader_posts(user, fetch),
            'category_list': get_category_list(),
            'categories': bitsettings.categories,
            'subcategories': bitsettings.subcategories,
            }
    return template_values



def get_email_text(email_name):
    """Retrieves the text of the email_name from the email_text.xml file.
    This would be extremely easy to make generic, but it hasn't been needed yet so it isn't.
    Use like get_email_text(email_name), where the email name is a string that matches one of the
    emails in email_text.xml.  Of course, there's currently only one email, but that could easily change.
    """
    xml_path = os.path.join( os.path.dirname(__file__), 'xml/email_text.xml' )
    tree = ElementTree.parse(xml_path)
    root = tree.getroot()
    for email in root.findall('email'):
            if email.get('name') == email_name:
                return email
##
# MainPage
# The MainPage is a listing of the 10 most recent posts in any subcategory in each of the categories.
# Along with that, it provides links to the category pages.
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
            'date': datetime.datetime.now(),
        }

        path = os.path.join( os.path.dirname(__file__), 'www/templates/main.html' )
        self.response.out.write( template.render( path, template_values ))

##
# Post, PostForm, and PostView form the basis of the listings side of the the application
# Post is the data model (below)
# PostForm is the create/update form.  If PostForm.get receives a valid postID parameter owned by the current user it edits the post, otherwise it creates a new post.
# PostView is the publically-available post on a GET request, and when POSTed to (by itself via the email form), sends an email to the post's owner.
# DeletePost simply removes the indicated object from the datastore
##

class PostForm(webapp2.RequestHandler):
    def get(self):
        user = users.get_current_user()
        if user:

            template_values = {
                'gvalues': get_global_template_vars(self, user),
            }

            if self.request.get('postID'):
                this_post = ndb.Key( urlsafe = self.request.get('postID') ).get()
                if this_post.traderID == str(user.email()):
                    # Only let the post's creator edit a post
                    # if this fails, a blank new-post form is loaded.
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
            # if the post exists (i.e. we're editing rather than creating), retrieve the post from the datastore
            post = ndb.Key( urlsafe = self.request.get('postID') ).get()
        else:
            # otherwise, create a new post, and add all the immutable details to it
            post = Post()
            post.traderID = str(user.email())
    
        # These items can be edited post-creation, as the post page changes over time, 
        # this list should also change to include everything in the form
        post.title = self.request.get('title')
        post.price = "%.8g" % float(self.request.get('price'))
        post.content = self.request.get('content')
        post.category = self.request.get('category')
        post.subcategory = self.request.get('subcategory')
        # note: post.engage and post.edit are not included here as they're auto_now_add and auto_now respectively

        if not post.postID:
            # if the post doesn't exist, create it, and assign the ID (which is the key) and the contact email (which is made of the key)
            postID = post.put()
            post.postID = postID.urlsafe()
            post.contact = post.postID + "@" + bitsettings.email_suffix
        # This either adds the post.postID/post.contact to the entity if they were just created, or updates the edited fields otherwise
        post.put()
        try:
            search.Index(name="posts").put( CreatePostDocument(
                                                    post.title, 
                                                    post.content,  
                                                    post.postID,
                                                    post.category,
                                                    post.subcategory,
                                                    post.price ) )
        except search.Error:
            pass


        self.redirect('/post?' + urllib.urlencode( {'postID' : post.postID } ) )


class PostView(webapp2.RequestHandler):
    def get(self):

        user = users.get_current_user()
        try:
            listing = ndb.Key( urlsafe = self.request.get('postID') ).get()
        except:
            listing = []
        template_values = {
            'gvalues': get_global_template_vars(self, user),
            'listing': listing,
        }

        path = os.path.join( os.path.dirname(__file__), 'www/templates/post.html' )
        self.response.out.write( template.render( path, template_values ))
    
    
    def post(self):
        """Sends an email from the postView page to the post's owner via the on-page form.
        """
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
            full_message = mail.EmailMessage(sender     = "%s <%s@%s>" % (bitsettings.site_name, bitsettings.email_local, bitsettings.email_suffix) ,
                                             subject    = "%s %s - %s" % ( bitsettings.email_subject, this_post.title, str(this_post.price) ) ,
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
                # if the trader and the post both exist, and the trader owns the post
                # they have the authority, so delete it and remove it from the index.
                post_index = search.Index(name="posts")
                post_index.delete(postID)
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
            'saved_queries' : SavedQuery.query( SavedQuery.userID == user.user_id() ).order( -SavedQuery.search_date ),
            'nickname' : user.nickname(),
            'user_id' : user.user_id(),
        }
            path = os.path.join( os.path.dirname(__file__), 'www/templates/trader.html' )
        else:
            # You can't have a page if you aren't logged in.
            template_values = {
            'gvalues': get_global_template_vars(self, user),
            }
            path = os.path.join( os.path.dirname(__file__), 'www/templates/not_logged_in.html' )
        

        self.response.out.write( template.render( path, template_values ))



class TraderPostView(webapp2.RequestHandler):
    def get(self):
        if users.get_current_user():
            user = users.get_current_user()
            user_id = user.email()
            # the cursor is required for pagination, as are next_cursor and more
            cursor = Cursor(urlsafe=self.request.get('cursor'))
            posts, next_cursor, more = Post.query(Post.traderID==user_id).order(-Post.engage).fetch_page(bitsettings.trader_fetch, start_cursor=cursor)
            if next_cursor != None:
                next_cursor = next_cursor.urlsafe()

            template_values = {
                'gvalues': get_global_template_vars(self, user),
                'posts' : posts,
                'next' : next_cursor,
                'more' : more,
                'date' : datetime.datetime.now(),
            }

            path = os.path.join( os.path.dirname(__file__), 'www/templates/trader_posts.html' )
        else:
            # You can't have posts if you aren't logged in.
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
        # This is the only place where I do this sooner rather than later.  
        # The template values get messy below, this allows the values to be assigned on the fly.
        template_values = {'gvalues': get_global_template_vars(self, user),}
        cursor = Cursor(urlsafe=self.request.get('cursor'))

        if not self.request.get('category'):
            # if there's no category selected, load the most recent posts from any category
            listings, next_cursor, more = Post.query().order(Post.subcategory).order(Post.category).fetch_page(bitsettings.category_fetch, start_cursor=cursor)
        else:
            category = self.request.get('category')
            template_values['category'] = category
            
            if self.request.get('subcategory'):
                # if there's a subcategory specified, narrow the query
                subcategory = self.request.get('subcategory')
                posts, next_cursor, more = Post.query(Post.category==category, Post.subcategory==subcategory).order(-Post.engage).fetch_page(bitsettings.category_fetch, start_cursor=cursor)
                if next_cursor != None:
                    next_cursor = next_cursor.urlsafe()
                template_values['next'] = next_cursor
                template_values['more'] = more
            else:
                listings = []
                for subcategory in bitsettings.subcategories:
                    query = Post.query(Post.category==category, Post.subcategory==subcategory["ID"]).order(-Post.engage).order(Post.subcategory).fetch(bitsettings.category_fetch//2)
                    for post in query:
                        listings.append(post)
                posts = sorted(listings, key=operator.attrgetter('subcategory'), reverse=False)
        template_values['posts'] = posts
        template_values['date'] = datetime.datetime.now()

        path = os.path.join( os.path.dirname(__file__), 'www/templates/posts.html' )
        self.response.out.write( template.render( path, template_values ))

##
# EmailReceived
# This acts as a receiver for all incoming email.  If the email matches the email for a post, the email is forarded to the post's owner.
##
class EmailReceived(InboundMailHandler):
    def post(self):
        message = mail.InboundEmailMessage(self.request.body)
        ## Get the traderID from the post based on the email address and "forward" the email
        this_post = Post.query(Post.contact==message.to).order(-Post.engage).get()
        email_to = this_post.traderID

        if mail.is_email_valid(email_to):
            email_messages = message.bodies('text/plain')
            email = get_email_text("Post Reply")
            
            for content_type, msg in email_messages:
                full_message = mail.EmailMessage(sender     = "%s <%s@%s>" % (bitsettings.site_name, bitsettings.email_local, bitsettings.email_suffix) ,
                                                 subject    = "%s %s - %s" % ( bitsettings.email_subject, this_post.title, str(this_post.price) ) ,
                                                 to         = "%s <%s>" % (email_to.split('@')[0], email_to) ,
                                                 reply_to   = message.sender ,
                                                 body       = email.find('header').text 
                                                 + "\n\n" + str(message.subject).upper() 
                                                 + "\n" + msg.decode() 
                                                 + "\n\n" + email.find('footer').text ,
                )
                full_message.send()


##
# SearchResults & SearchMemory
# SearchResults handles the search page functions
# SearchMemory handles the saved searches (and presumably the alerts)
##

class SearchResults(webapp2.RequestHandler):
    def get(self):
        if self.request.get('q'):
            query = str(self.request.get('q'))
        else:
            query = ""

        q=query ## The query is modified below, so q is the original query string

        if self.request.get('p'):
            cursor = search.Cursor(web_safe_string=self.request.get('p'))
        else:
            cursor = search.Cursor()

        template_values = {}

        if self.request.get('category'):
            category = self.request.get('category')
            query += " category:%s" % category
            template_values['query_category'] = category
        if self.request.get('subcategory'):
            subcategory = self.request.get('subcategory')
            query += " subcategory:%s" % subcategory
            template_values['query_subcategory'] = subcategory

        query_options = search.QueryOptions(
            limit=bitsettings.search_per_page,
            cursor=cursor,
            sort_options=None
            )


        query_obj = search.Query(query_string=query, options=query_options)
        results = search.Index(name="posts").search(query=query_obj)
        posts = []

        for doc in results:
            this_post = ndb.Key( urlsafe = doc.doc_id ).get()
            posts.append(this_post)

        if users.get_current_user():
            user = users.get_current_user()
            template_values['gvalues'] = get_global_template_vars(self, user)
        else:
            template_values['gvalues'] = get_global_template_vars(self)

        template_values['posts'] = posts           
        template_values['date'] = datetime.datetime.now()
        try:
            template_values['next'] = results.cursor.web_safe_string
            logging.info(template_values['next'])
        except AttributeError:
            template_values['end'] = True
        template_values['query'] = q

        path = os.path.join( os.path.dirname(__file__), 'www/templates/search_results.html' )
        
        self.response.out.write( template.render( path, template_values ))

class SearchMemory(webapp2.RequestHandler):
    def get(self):
        if users.get_current_user():
            user = users.get_current_user()
            user_id = user.user_id()
            query_key = self.request.get('ID')
            match = ndb.Key(urlsafe=query_key).get()
            if match.userID == user_id:
                ndb.Key(urlsafe=query_key).delete()
        self.redirect('/trader')

    def post(self):

        if users.get_current_user():
            user = users.get_current_user()
            user_id = user.user_id()
            
            query = self.request.get('q') if self.request.get('q') else ""
            category = self.request.get('category')
            subcategory = self.request.get('subcategory')

            if (query or category or subcategory):
                
                query_to_save = SavedQuery()
                query_to_save.populate(userID = user_id,
                                            q = query,
                                     category = category,
                                  subcategory = subcategory,
                                         name = "" )
                query_to_save.queryID = query_to_save.put().urlsafe()
                query_to_save.put()


            self.redirect('/trader')

        else:
            # You can't save a search if you aren't logged in.
            template_values = {
                'gvalues': get_global_template_vars(self),
            }
            path = os.path.join( os.path.dirname(__file__), 'www/templates/not_logged_in.html' )
        
            self.response.out.write( template.render( path, template_values ))

##
# Search Documents
# https://developers.google.com/appengine/docs/python/search/overview
##
def CreatePostDocument(title, content, postID, category, subcategory, price):
    return search.Document(doc_id=postID,
        fields=[search.TextField( name='title'  , value=title ),
                search.TextField( name='content', value=content ),
                search.AtomField( name='category', value=category ),
                search.AtomField( name='subcategory', value=subcategory ),
                search.NumberField( name='price', value=float(price) )
        ])

##
# Data Models
#
##

class Post(ndb.Model):
    postID = ndb.StringProperty()                       # URL-safe NDB key
    traderID = ndb.StringProperty()                     # OpenID email of user who posted
    title = ndb.TextProperty()
    price = ndb.StringProperty()
    content = ndb.TextProperty()
    engage = ndb.DateTimeProperty(auto_now_add=True)    # datetime of inital post
    edit = ndb.DateTimeProperty(auto_now=True)          # datetime of intial post & all edits
    contact = ndb.StringProperty()                      # public email attached to post
    category = ndb.StringProperty()
    subcategory = ndb.StringProperty()

class SavedQuery(ndb.Model):    
    userID = ndb.StringProperty()
    queryID = ndb.StringProperty()
    q = ndb.StringProperty()
    category = ndb.StringProperty()
    subcategory = ndb.StringProperty()
    name = ndb.StringProperty()
    search_date = ndb.DateTimeProperty(auto_now=True)


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
                                ( '/search'       , SearchResults ),                                
                                ( '/search/memory', SearchMemory ),
                                ],
                            debug = True)

def main():
    run_wsgi_app(app)

if __name__ == '__main__':
    main()