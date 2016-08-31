import os
import logging
import string
import re
import urllib2
import cgi
import jinja2
import webapp2
import random

from datetime import datetime, timedelta
from pytz.gae import pytz
from pytz import timezone

from google.appengine.ext import ndb
from google.appengine.api import mail

from google.appengine.ext.webapp.mail_handlers import BounceNotification
from google.appengine.ext.webapp.mail_handlers import BounceNotificationHandler

from bs4 import BeautifulSoup

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

class Author(ndb.Model):
    """A model for representing a person who has set up an alert with the service.

    Attributes:
        email: A string representing the domain username of the Author (i.e. the part before @wellesley.edu)
        date: A datetime representing the time the Author was added to the database
        user_id: A 16 character random string representing a unique identifier for this Author. Used for more secure URLs.
    """
    email = ndb.StringProperty(indexed=True, required=True)
    date = ndb.DateTimeProperty(auto_now_add=True, indexed=True) #so can autoremove subscriptions over 4 years old (after graduation)
    user_id = ndb.StringProperty(indexed=True)
    def create_ID(self, email):
        return ''.join(random.choice(string.ascii_letters) for i in range(16))+email

    

class Dish(ndb.Model):
    """A model for representing an individual food item.

    Attributes:
        dish_name: A string representation of this food item's name.
        authors: A list of the Author objects who have subscribed to be notified when this Dish appears again.
    """

    dish_name = ndb.StringProperty(required=True)
    authors = ndb.StructuredProperty(Author, repeated=True)

DEFAULT_DISH_NAME = 'default_dish'
DEFAULT_DISH = Dish(dish_name=DEFAULT_DISH_NAME, authors=[]) #parent of all Dish entities so we can have strongly-consistent results


class DiningHall:
    """A representation of a dining hall serving food on campus.

    Attributes:
        name: A string which is the nickname/name of the dining hall.
        food_items: A list of strings for each Dish being served today at the dining hall.
        is_open: A boolean corresponding to whether this dining hall is currently open (i.e. serving food) or not.
    """

    def __init__(self, hall_name, menus, local_tz):
        """Initializes this with name and reads and parses food items from each URL in menus.

        Args:
            hall_name: A string that is the dining hall's name/nickname.
            menus: A list of strings corresponding to the URL where each dining hall's food info is posted.
            local_tz: A datetime object for the local time zone (in this case, America/New_York)
        """

        if hall_name == "lulu":
            self.name = "lulu"
            self.food_items=[] 
            self.food_items = self.get_food_items(menus[0])
            self.is_open = self.lulu_open(local_tz)
        elif hall_name == "bates":
            self.name = "bates"
            self.food_items=[]
            self.food_items = self.get_food_items(menus[1])
            self.is_open = self.bpt_open(local_tz)
        elif hall_name == "pom":
            self.name = "pom"
            self.food_items=[]
            self.food_items = self.get_food_items(menus[2])
            self.is_open = self.bpt_open(local_tz)
        elif hall_name == "stone":
            self.name = "stone"
            self.food_items=[]
            self.food_items = self.get_food_items(menus[3])
            self.is_open = self.stone_open(local_tz)
        elif hall_name == "tower":
            self.name = "tower"
            self.food_items=[]
            self.food_items = self.get_food_items(menus[4])
            self.is_open = self.bpt_open(local_tz)
        else:
            logging.debug("INVALID DINING HALL")
            self.name = "INVALID DINING HALL"
            self.food_items = []
            self.is_open = False

    def get_food_items(self, hall_url):
        """Scrapes food items from the menu at hall_url.
        Adds bolded non-food categories to the list prepended by *b*.

        Args:
            hall_url: A string which is the URL where the daily menu is posted for a dining hall.

        Returns:
            A cleaned list of the food items and categories parsed from hall_url. This may be empty.
        """
        bold_items = []
        try:
            hall = urllib2.urlopen(hall_url).read()
            hall_soup = BeautifulSoup(hall).div

            for node in hall_soup.findAll('p'):
                self.food_items.append(''.join(node.findAll(text=True)).encode('utf-8'))

            for node in hall_soup.findAll('b'):
                bold_items.append(''.join(node.findAll(text=True)).encode('utf-8'))

        except urllib2.HTTPError as e:
            logging.warning("HTTP Error. Code:")
            logging.warning(e.code)
            logging.warning(e)
            
        except urllib2.URLError as e:
            logging.warning("URL Error (not HTTP):")
            logging.warning(e.args)

        return self.clean_list(bold_items)

    def clean_list(self, bold_items):
        """Cleans up self.food_items by removing irrelevant words and characters and splitting up by commas and semi-colons.

        Args:
            bold_items: A list of strings which were between <b> tags in the HTML that was scraped for food items.
                We assume these items are categories and non-food.

        Returns:
            A list of strings corresponding to food_items and bold_items that have been cleaned and combined
            with each bold item prepended by *b*.
        """
        keywords = [" if ", "Offered Daily:", "Offered", "Offered daily", "Offered daily:",  "Daily", "daily", "!supportLineBreakNewLine", "endif", "Served", "served", "served daily"]
        alphabet = []
        for p in range(len(string.ascii_letters)):
            alphabet.append(string.ascii_letters[p])

        temp = []

        for i in range(len(bold_items)):
            b = bold_items[i]

            b = b.replace(b'\r\n', ' ').replace(b'\xc2\xa0', ' ').replace(b'\xe2\x80\x99', '\'').replace(b'\xc2\x92', '\'').replace(b'\x26', '&amp;')
            b = b.replace('-','')
            b = re.sub("[\(\[].*?[\)\]]", "", b) #removes stuff between parentheses and brackets
            b = ' '.join(b.split()) #removes more than one space between words
            b = "".join([x if ord(x) < 128 else '' for x in b]) #removes non-ASCII characters
            b = b.strip()
            bold_items[i] = b

        bold_items = filter(lambda x: len(x)>1, bold_items)

        if 'From' in bold_items:
            bold_items.remove('From')
            if 'the Grill' in bold_items:
                bold_items.remove('the Grill')
                bold_items.append('From the Grill')
        
        # to avoid making tons of 'dinner' categories instead of e.g. 'pure dinner'
        if 'Lunch' in bold_items:
            bold_items.remove('Lunch')
            bold_items.append('Lunch')

        if 'Dinner' in bold_items:
            bold_items.remove('Dinner')
            bold_items.append('Dinner')

        for i in self.food_items:
            i = i.replace(b'\r\n', ' ').replace(b'\xc2\xa0', ' ').replace(b'\xe2\x80\x99', '\'').replace(b'\xc2\x92', '\'').replace(b'\x26', '&')
            i = re.sub("[\(\[].*?[\)\]]", "", i) #removes stuff between parentheses and brackets
            i = ' '.join(i.split()) #removes more than one space between words
            i = i.replace(" and", ',').replace(b'\x2D', '-').replace("or ", ',').replace('<', '').replace('>', '') #sometimes the and-replacement is tricky
            i = i.replace('- ','').replace('-','')

            for k in keywords:
                i = i.replace(k, '')

            for b in bold_items:
                if b in i:
                    i_b=i
                    i = i.replace(b, ','+b+',')
                    #logging.info(self.name+str(bold_items)+'\n'+i_b+'\n'+i+'-----------\n')
                    break
            for b in bold_items: #b/c of issue with Tower having bolded menu categories in same paragraph as foods 
                if len(b)>1:
                    if b.lower()=="grill": #grumble grumble     
                        try:
                            b_index = i.index(b)+len(b)
                            two_char_after = i[b_index:b_index+2]
                            if two_char_after!="ed":
                                i = i.replace(b, b+',')
                        except ValueError:
                            pass
                    else:
                        i = i.replace(b, ', '+b+',')
            
            i = "".join([x if ord(x) < 128 else '' for x in i]) #removes non-ASCII characters

            i = i.replace("Hard Boiled Eggs", "Hard-boiled Eggs").replace("Hardboiled Eggs", "Hard-boiled Eggs") #neurotic grammatical consistency

            i = i.strip()

            pos_list = i.split(",")
            for p in pos_list:
                p = p.strip()
                if "closed" in p.lower(): #for Stone-Davis
                    temp.append("*b*"+p)
                elif p.lower() not in keywords and len(p)>1 and p[0] in alphabet and p not in bold_items:
                    if p.find(';')==-1:
                        temp.append(p)
                    else: # we have a sublist with a semicolon
                        sublist = p.split(';')
                        for x in sublist:
                            x = x.strip()
                            if "closed" in x.lower() and x not in temp:
                                temp.append("*b*"+x)
                            elif x not in temp and x.lower() not in keywords and len(x)>1 and x[0] in alphabet and x not in bold_items:
                                temp.append(x)
                            elif len(x)>1 and x in bold_items:
                                temp.append("*b"+x)
                elif len(p)>1 and p in bold_items:
                    temp.append("*b*"+p)  #so we can remember not to call p a food item


        if len(temp)==0:
            temp.append("*b*No items found")
        return temp

    def bpt_open(self, real_localtz):
        """Determines whether Bates, Pomeroy, and Tower dining halls are currently open.

        Based on Wellesley Fresh hours of operations http://www.wellesleyfresh.com/pdfs/wellesley_hours_of_ops.pdf
        as of August 2016.

        Args:
            real_localtz: A datetime object that is date aware to America/New_York timezone.

        Returns:
            A boolean of whether Bates, Pomeroy, and Tower are currently open.
        """
        hour = real_localtz.hour 
        minute = real_localtz.minute

        hm_sum = hour + (minute/60.0)

        day_of_week = real_localtz.isoweekday() #mon = 1; sun = 7

        if day_of_week==6 or day_of_week==7: #saturday and sunday hours
            return (hm_sum>=8.5 and hm_sum<=14) or (hm_sum>=17 and hm_sum<=18.5)

        return (hm_sum>=7 and hm_sum<=10) or (hm_sum>=11.5 and hm_sum<=14) or (hm_sum>=17 and hm_sum<=19)

    def lulu_open(self, real_localtz):
        """Determines whether Lulu (Bae Pao Lulu Chow) dining hall is currently open.

        Based on Wellesley Fresh hours of operations http://www.wellesleyfresh.com/pdfs/wellesley_hours_of_ops.pdf
        as of August 2016.

        Args:
            real_localtz: A datetime object that is date aware to America/New_York timezone.

        Returns:
            A boolean of whether Lulu is currently open.
        """
        hour = real_localtz.hour 
        minute = real_localtz.minute

        hm_sum = hour + (minute/60.0)

        return (hm_sum>=7 and hm_sum<=10) or (hm_sum>=11.5 and hm_sum<=14) or (hm_sum>=17 and hm_sum<=22)
        
    def stone_open(self, real_localtz):
        """Determines whether Stone-Davis dining hall is currently open.

        Based on Wellesley Fresh hours of operations http://www.wellesleyfresh.com/pdfs/wellesley_hours_of_ops.pdf
        as of August 2016.

        Args:
            real_localtz: A datetime object that is date aware to America/New_York timezone.

        Returns:
            A boolean of whether Stone-Davis is currently open.
        """
        day_of_week = real_localtz.isoweekday() #mon = 1; sun = 7
        
        hour = real_localtz.hour 
        minute = real_localtz.minute

        hm_sum = hour + (minute/60.0)

        if day_of_week==6 or day_of_week==7:
            return False
        if day_of_week==5:
            return (hm_sum>=7 and hm_sum <=10) or (hm_sum>=11.5 and hm_sum<=14) or (hm_sum>=5 and hm_sum<=19)
        return self.lulu_open(real_localtz)


def menu_urls(real_localtz):
    """Returns a list of the URLs where the menus for Wellesley dining halls can be found.

    Args:
        real_localtz: A datetime object aware to the local timezone of America/New_York.

    Returns:
        A list of strings corresponding to the URL location of each of the Wellesley dining halls.
    """
    dd = "%d" % (real_localtz.day)
    mm = "%d" % (real_localtz.month)

    if len(dd) < 2:
        dd = "0"+dd
    if len(mm) < 2:
        mm = "0"+mm

    menus = ['menus/bplc/menu_'+mm+dd+'.htm','menus/bates/menu_'+mm+dd+'.htm','menus/pomeroy/menu_'+mm+dd+'.htm']
    menus.append('menus/stonedavis/menu_'+mm+dd+'.htm')
    menus.append('menus/tower/menu_'+mm+dd+'.htm')

    for i in range(len(menus)):
        menus[i] = "http://www.wellesleyfresh.com/"+menus[i]

    return menus

def emp_is_open(real_localtz):
    """Determines whether the Emporium is currently open.

    Based on Wellesley Fresh hours of operations http://www.wellesleyfresh.com/pdfs/wellesley_hours_of_ops.pdf
        as of August 2016.

    Args:
        real_localtz: A datetime object aware to the local timezone of America/New_York.

    Returns:
        A boolean of whether the Emporium is currently open.
    """
    hour = real_localtz.hour 
    minute = real_localtz.minute

    hm_sum = hour + (minute/60.0)

    day_of_week = real_localtz.isoweekday() #mon = 1; sun = 7

    if day_of_week==1 or day_of_week==5:
        return hm_sum>=7 and hm_sum<=20
    elif day_of_week==2 or day_of_week==3 or day_of_week==4:
        return hm_sum>=7 and hm_sum<=23.9999 #midnight but...
    else:
        return hm_sum>=12 and hm_sum<=20

def lb_is_open(real_localtz):
    """Determines whether The Leaky Beaker is currently open.

    Based on Wellesley Fresh hours of operations http://www.wellesleyfresh.com/pdfs/wellesley_hours_of_ops.pdf
        as of August 2016.

    Args:
        real_localtz: A datetime object aware to the local timezone of America/New_York.

    Returns:
        A boolean of whether The Leaky Beaker is currently open.
    """
    day_of_week = real_localtz.isoweekday() #mon = 1; sun = 7

    if day_of_week==6 or day_of_week==7:
        return False

    hour = real_localtz.hour 
    minute = real_localtz.minute

    hm_sum = hour + (minute/60.0)

    return hm_sum>=8 and hm_sum<=16

def collins_cafe_is_open(real_localtz):
    """Determines whether Collins Cafe is currently open.

    Based on Wellesley Fresh hours of operations http://www.wellesleyfresh.com/pdfs/wellesley_hours_of_ops.pdf
        as of August 2016.

    Args:
        real_localtz: A datetime object aware to the local timezone of America/New_York.

    Returns:
        A boolean of whether Collins Cafe is currently open.
    """
    day_of_week = real_localtz.isoweekday() #mon = 1; sun = 7

    if day_of_week==6 or day_of_week==7:
        return False

    hour = real_localtz.hour 
    minute = real_localtz.minute

    hm_sum = hour + (minute/60.0)

    return hm_sum>=8 and hm_sum<=14

class MainPage(webapp2.RequestHandler):
    """Renders the main page of the Wellesley Daily Dish application with the current menu for each dining hall displayed."""

    def get(self):
        template = JINJA_ENVIRONMENT.get_template('index.html')

        now = datetime.utcnow()
        now = now.replace(tzinfo=pytz.utc)
        real_localtz = datetime.astimezone(now, pytz.timezone('America/New_York'))

        menus = menu_urls(real_localtz)

        lulu = DiningHall("lulu", menus, real_localtz)
        bates = DiningHall("bates", menus, real_localtz)
        pom = DiningHall("pom", menus, real_localtz)
        stone = DiningHall("stone", menus, real_localtz)
        tower = DiningHall("tower", menus, real_localtz)

        date_day = real_localtz.strftime("%d")
        if date_day[0]=='0':
            date_string = real_localtz.strftime("%A, %B "+date_day[1])
        else:
            date_string = real_localtz.strftime("%A, %B %d")

        emporium_is_open = emp_is_open(real_localtz)
        leaky_beaker_is_open = lb_is_open(real_localtz)
        collins_is_open = collins_cafe_is_open(real_localtz)

        template_values = {
            "date_string" : date_string,
            "lulu" : lulu,
            "bates" : bates,
            "pom" : pom,
            "stone" : stone,
            "tower" : tower,
            "emporium_is_open" : emporium_is_open,
            "leaky_beaker_is_open" : leaky_beaker_is_open,
            "collins_is_open" : collins_is_open
        }

        self.response.write(template.render(template_values))
 

class DishHandler(webapp2.RequestHandler):
    """Sets up new email alerts and redirects to a confirmation page showing the user's subscription info."""

    def get(self):
        """Confirmation of the submission's success.

        Shows all dishes the user with currentEmail is set up to receive alerts about.
        """
        try:
            currentEmail = Author.query().filter(Author.user_id == cgi.escape(self.request.get("id"))).get().email
        except AttributeError as e:
            logging.info(e)
            currentEmail = ""
        submit_template = JINJA_ENVIRONMENT.get_template('submission.html')

        template_values = {}
        template_values["foods"] = []
        subbedDishes = Dish.query(ancestor=DEFAULT_DISH.key).filter(Dish.authors.email == currentEmail).fetch() #gets dishes who have `user` as someone signed up for alerts
        foods = [d.dish_name for d in subbedDishes] 
        
        for f in foods:
            template_values["foods"].append(f)
        template_values["emailaddress"] = currentEmail

        self.response.out.write(submit_template.render(template_values))

    def post(self):
        """Adds to the database an Author with currentEmail to each checked Dish's list of authors."""
        new_user_created = False
        currentEmail = cgi.escape(self.request.get("emailaddress"))
        user = Author.query().filter(Author.email == currentEmail).get()
        if not user:
            user = Author(email=currentEmail)
            user.user_id = user.create_ID(currentEmail)
            new_user_created = True
        key = user.put()

        for item in self.request.arguments():
            if item!="emailaddress":
                dish_name_query = Dish.query(ancestor=DEFAULT_DISH.key).filter(Dish.dish_name == item).get() #should only be one Dish entry with "item" name

                if not dish_name_query: #true if dish_name_query hasn't had an alert set up for it yet
                    new_dish = Dish(parent=DEFAULT_DISH.key, dish_name=item, authors=[])
                    new_dish.authors.append(user)
                    dish_name_query = new_dish
                else:
                    old_authors = dish_name_query.authors
                    if not self.__author_found(user.email, old_authors): #to avoid duplicate authors on the list
                        old_authors.append(user)
                    dish_name_query.authors = old_authors

                dish_name_query.put()
        if new_user_created:
            logging.info("New user sign up %s" % currentEmail)
            self.__send_welcome_email(currentEmail, key)
        self.redirect('/submission/?id='+user.user_id)

    def __author_found(self, author_email, author_list):
        for person in author_list:
            if person.email==author_email:
                return True
        return False

    def __send_welcome_email(self, email, user_key):
        """Sends a welcome email the first time someone sets up an alert on the site.

        Args:
            email: A string representing the domain username of the person who signed up.
        """
        user_ubsub_link = "wellesley-daily-dish.appspot.com/unsubscribe/?id="+user_key.get().user_id
        email_body = "Hi, %s!\n\nThanks for signing up on Wellesley Daily Dish!" % email
        email_body += "\n\nUpdate your subscription preferences using this link: "+user_ubsub_link

        mail.send_mail("Wellesley Daily Dish <welcome@wellesley-daily-dish.appspotmail.com>",
                email+"@wellesley.edu",
                "Welcome!",
                email_body,
                headers = {"List-Unsubscribe": "https://"+user_ubsub_link}
                )


class EmailAlertHandler(webapp2.RequestHandler):
    """Sends out emails to everyone who has a subscribed food appearing in a dining hall tomorrow."""

    def get(self):
        """Gets food items appearing in all the dining halls tomorrow and sends emails to each person signed up
        to be alerted about their presence.

        Only one email per person will be sent out daily. It has a summary of all subscribed foods appearing tomorrow.
        """
        emails_to_send = {}

        now = datetime.utcnow()
        now = now.replace(tzinfo=pytz.utc)
        tomorrow_localtz = datetime.astimezone(now, pytz.timezone('America/New_York')) + timedelta(days=1) 

        tomorrow_menu_URLS = menu_urls(tomorrow_localtz)

        lulu_tmrw = DiningHall("lulu", tomorrow_menu_URLS, tomorrow_localtz)
        bates_tmrw = DiningHall("bates", tomorrow_menu_URLS, tomorrow_localtz)
        pom_tmrw = DiningHall("pom", tomorrow_menu_URLS, tomorrow_localtz)
        stone_tmrw = DiningHall("stone", tomorrow_menu_URLS, tomorrow_localtz)
        tower_tmrw = DiningHall("tower", tomorrow_menu_URLS, tomorrow_localtz)

        all_hall_tmrw = [lulu_tmrw, bates_tmrw, pom_tmrw, stone_tmrw, tower_tmrw]

        for dHall in all_hall_tmrw:
            for fI in dHall.food_items:
                fI_query = Dish.query(ancestor=DEFAULT_DISH.key).filter(Dish.dish_name == fI).get()
                
                if fI_query: #true if anyone has alerts set up for fI_query (or has at some point)
                    ppl_to_alert = [a.email for a in fI_query.authors]
                    for person_email in ppl_to_alert:
                        if emails_to_send.has_key(person_email): #true if an email alert is already in progress
                            old_email_body = emails_to_send[person_email]
                            old_email_body += "\n%s will be at " % fI
                            old_email_body += self.neaten(dHall.name)+" tomorrow" 
                            emails_to_send[person_email] = old_email_body
                        else:
                            tomorrow_day = tomorrow_localtz.strftime("%d")
                            if tomorrow_day[0]=='0':
                                tomorrow_date = tomorrow_localtz.strftime("%A, %B "+tomorrow_day[1])
                            else:
                                tomorrow_date = tomorrow_localtz.strftime("%A, %B %d")
                            email_body = "Hi, %s!\n\nGood news.\n\n" % person_email
                            email_body += fI+" will be at "+self.neaten(dHall.name)+" tomorrow ("+tomorrow_date+")"
                            emails_to_send[person_email] = email_body

        for email in emails_to_send:
            user_ubsub_link = "wellesley-daily-dish.appspot.com/unsubscribe/?id="+Author.query().filter(Author.email==email).get().user_id

            email_body = emails_to_send[email] + "\n\nUpdate your subscription preferences using this link: "+user_ubsub_link
            emails_to_send[email] = email_body

            logging.info("Sent email to %s: %s" % (email,email_body))

            mail.send_mail("Wellesley Daily Dish <alerts@wellesley-daily-dish.appspotmail.com>",
                "%s@wellesley.edu" % email,
                "Dining Hall Favs Tomorrow!",
                emails_to_send[email],
                headers = {"List-Unsubscribe": "https://"+user_ubsub_link}
                )

    def neaten(self, dHallName):
        dHallName = dHallName.title()
        if dHallName == "Pom":
            return "Pomeroy"
        if dHallName == "Stone":
            return "Stone-Davis"
        return dHallName


def removeAuthorFrmDish(dish, username):
    """Removes Author with invalid email from the list of authors on a dish they have signed up to be alerted about.

    Args:
        dish: A Dish object stored in the database which has an Author with email username on its list of authors.
        username: A string representing the invalid email of username@wellesley.edu.
    """
    authorList = dish.authors
    for i in range(len(authorList)):
        if authorList[i].email == username:
            authorList.pop(i)
            break
    dish.authors = authorList
    dish.put() #updates entry

class LogBounceHandler(webapp2.RequestHandler):
    """Handles a bounce notification about an email alert sent out and purges the database of all alerts for the offending email."""

    def post(self):
        """Receives a bounce notification for username@wellesley.edu and goes through database cleaning the email out of Dish.authors."""
        post_vars = self.request.POST
        #bounce = BounceNotification(post_vars)
        username = post_vars["original-to"]
        logging.info("So "+username+" is an invalid email and we should remove all entries for it")
        username = username.split("@wellesley.edu")[0] #domain username

        dishes = [d for d in Dish.query(ancestor=DEFAULT_DISH.key).filter(Dish.authors.email == username).fetch()] #gets Dishes who have `username` as someone signed up for alerts

        for dish in dishes:
            removeAuthorFrmDish(dish, username)

        user = Author.query().filter(Author.email == username).get()
        if not user:
            logging.info("Error finding %s Author in DB" % username)
        else:
            user.key.delete()
            logging.info("Removed Author %s and associated dishes" % username)


class UnsubscribeHandler(webapp2.RequestHandler):
    """Displays a subscription preferences page and allows users to unsubscribe from some or all food item alerts."""

    def get(self):
        """Displays an unsubscribe page with checked checkboxes for each item the user with currentEmail is subscribed to."""
        try:
            currentEmail = Author.query().filter(Author.user_id == cgi.escape(self.request.get("id"))).get().email
        except AttributeError as e:
            logging.info(e)
            currentEmail = ""
        submit_template = JINJA_ENVIRONMENT.get_template('unsubscribe_page.html')

        template_values = {}
        template_values["foods"] = []
        subbedDishes = Dish.query(ancestor=DEFAULT_DISH.key).filter(Dish.authors.email == currentEmail).fetch() #gets dishes who have `user` as someone signed up for alerts
        foods = [d.dish_name for d in subbedDishes] 
        
        for f in foods:
            template_values["foods"].append(f)
        template_values["email"] = currentEmail
        template_values["id"] = cgi.escape(self.request.get("id"))

        self.response.out.write(submit_template.render(template_values))

    def post(self):
        """Unsubscribes the Author with currentEmail from all unchecked boxes when submit button pressed.
        Then redirects to a success page.
        """
        submit_template = JINJA_ENVIRONMENT.get_template('unsubscribe_success.html')
        template_values = {}

        try:
            currentEmail = Author.query().filter(Author.user_id == cgi.escape(self.request.get("id"))).get().email
        except AttributeError as e:
            logging.info("Error unsubscribing")
            logging.info(e)
            currentEmail = ""

        subbedDishes = Dish.query(ancestor=DEFAULT_DISH.key).filter(Dish.authors.email == currentEmail).fetch()
        allSubbedItems = [d.dish_name for d in subbedDishes]
        checkedItems = [chItem for chItem in self.request.arguments() if chItem!="id"]
        itemsToUnsub = [un for un in allSubbedItems if un not in checkedItems] #inefficient... there are apparently some clever JS tricks

        for item in itemsToUnsub:
            dish = Dish.query(ancestor=DEFAULT_DISH.key).filter(Dish.dish_name == item).get()
            removeAuthorFrmDish(dish, currentEmail)
        logging.info("Unsubscribed "+currentEmail+" from "+", ".join(itemsToUnsub))
        self.response.out.write(submit_template.render(template_values))


application = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/submission/', DishHandler),
    ('/tasks/send_alerts', EmailAlertHandler),
    ('/_ah/bounce', LogBounceHandler),
    ('/unsubscribe/', UnsubscribeHandler)
], debug=True)