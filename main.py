import os, logging, string, re
import urllib2
import cgi

import jinja2
import webapp2
from datetime import datetime, timedelta
from pytz.gae import pytz
from pytz import timezone
import urllib

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
    """A model for representing the person whose email is stored in a Dish"""
    email = ndb.StringProperty(indexed=True, required=True)
    date = ndb.DateTimeProperty(auto_now_add=True, indexed=True) #so can autoremove subscriptions over 4 years old (after graduation)

class Dish(ndb.Model):
    """A main model for representing an individual food item"""
    dish_name = ndb.StringProperty(required=True)
    authors = ndb.StructuredProperty(Author, repeated=True)

DEFAULT_DISH_NAME = 'default_dish'
DEFAULT_DISH = Dish(dish_name=DEFAULT_DISH_NAME, authors=[]) #can be parent of all dishes so we can have strongly-consistent results

class DiningHall:

    def __init__(self, hall_name, menus, local_tz):
        if hall_name == "lulu":
            self.name = "lulu"
            self.food_items=[] 
            self.food_items = self.getFoodItems(menus[0])
            self.isOpen = self.luluOpen(local_tz)
        elif hall_name == "bates":
            self.name = "bates"
            self.food_items=[]
            self.food_items = self.getFoodItems(menus[1])
            self.isOpen = self.bptOpen(local_tz)
        elif hall_name == "pom":
            self.name = "pom"
            self.food_items=[]
            self.food_items = self.getFoodItems(menus[2])
            self.isOpen = self.bptOpen(local_tz)
        elif hall_name == "stone":
            self.name = "stone"
            self.food_items=[]
            self.food_items = self.getFoodItems(menus[3])
            self.isOpen = self.stoneOpen(local_tz)
        elif hall_name == "tower":
            self.name = "tower"
            self.food_items=[]
            self.food_items = self.getFoodItems(menus[4])
            self.isOpen = self.bptOpen(local_tz)
        else:
            logging.debug("INVALID DINING HALL")
            self.name = "INVALID DINING HALL"

    def getFoodItems(self, hallUrl):
        bold_items = []

        try:
            hall = urllib2.urlopen(hallUrl).read()
            hall_soup = BeautifulSoup(hall).div

            for node in hall_soup.findAll('p'):
                self.food_items.append(''.join(node.findAll(text=True)).encode('utf-8'))

            for node in hall_soup.findAll('b'):
                bold_items.append(''.join(node.findAll(text=True)).encode('utf-8'))

        except urllib2.HTTPError as e:
            logging.warning("HTTP Error:")
            logging.warning(e.code)
            
        except urllib2.URLError as e:
            logging.warning("URL Error (not HTTP):")
            logging.warning(e.args)

        return self.cleanList(bold_items)

    def cleanList(self, bold_items):
        keywords = [" if ", "Offered Daily:", "Offered", "Offered daily", "Offered daily:",  "!supportLineBreakNewLine", "endif", "Served", "Daily", "daily", "served"]
        #keywords += ["HomeStyle", "Home-style Dinner", "Homestyle Lunch", "Homestyle lunch", "Homestyle Dinner", "Homestyle dinner", "Late Night", "Late Nite", "Late night", "Hot Bar", "hot bar", "Hot bar", "Home-style Lunch", "Continental","breakfast", "Brunch", "Dinner"]
        #keywords += ["Lunch", "Breakfast", "Pizza/Pasta", "Pizza/pasta", "Pure", "pure","continental", "brunch", "lunch", "dinner", "grill", "fusion", "daily", "continental breakfast", "soup", "pizza", "homestyle", "home-style"]
        alphabet = []
        for p in range(len(string.ascii_letters)):
            alphabet.append(string.ascii_letters[p])

        temp = []

        for i in range(len(bold_items)):
            b = bold_items[i]
            b = b.replace(b'\r\n', ' ').replace(b'\xc2\xa0', ' ').replace(b'\xe2\x80\x99', '\'').replace(b'\xc2\x92', '\'').replace(b'\x26', '&amp;')
            b = re.sub("[\(\[].*?[\)\]]", "", b) #removes stuff between parentheses and brackets
            b = ' '.join(b.split()) #removes more than one space between words
            b = "".join([x if ord(x) < 128 else '' for x in b])
            b = b.strip()
            bold_items[i] = b

        for i in self.food_items:
            i = i.replace(b'\r\n', ' ').replace(b'\xc2\xa0', ' ').replace(b'\xe2\x80\x99', '\'').replace(b'\xc2\x92', '\'').replace(b'\x26', '&')
            i = re.sub("[\(\[].*?[\)\]]", "", i) #removes stuff between parentheses and brackets
            i = ' '.join(i.split()) #removes more than one space between words
            i = i.replace(" and", ',').replace(b'\x2D', '-').replace("or ", ',') #sometimes the and-replacement is tricky

            for k in keywords:
                i = i.replace(k, '')

            for b in bold_items: #solving issue with Tower having bolded menu categories in same paragraph as foods 
                if len(b)>1:
                    i = i.replace(b, b+',')
            
            i = "".join([x if ord(x) < 128 else '' for x in i])

            i = i.replace("Hard Boiled Eggs", "Hard-boiled Eggs").replace("Hardboiled Eggs", "Hard-boiled Eggs") #neurotic grammatical consistency

            i = i.strip()

            pos_list = i.split(",")
            for p in pos_list:
                p = p.strip()
                if p.lower() not in keywords and len(p)>1 and p[0] in alphabet and p not in bold_items:
                    temp.append(p)
                elif len(p)>1 and p in bold_items:
                    temp.append("*b*"+p) 

            pos_list = i.split(";")
            if len(pos_list) > 1:
                temp.pop() #means we found a list separated by semi-colons and don't want the original list to be added as one item
                for p in pos_list:
                    p = p.strip()
                    if p not in temp and p.lower() not in keywords and len(p)>1 and p[0] in alphabet and p not in bold_items:
                        temp.append(p)
                    elif len(p)>1 and p in bold_items:
                        temp.append("*b"+p)

        return temp

    def bptOpen(self, real_localtz):
        hour = real_localtz.hour 
        minute = real_localtz.minute

        hm_sum = hour + (minute/60.0)

        day_of_week = real_localtz.isoweekday() #mon = 1; sun = 7

        if day_of_week==6 or day_of_week==7: #saturday and sunday hours
            return (hm_sum>=8.5 and hm_sum<=14) or (hm_sum>=17 and hm_sum<=18.5)

        return (hm_sum>=7 and hm_sum<=10) or (hm_sum>=11.5 and hm_sum<=14) or (hm_sum>=17 and hm_sum<=19)

    def luluOpen(self, real_localtz):
        hour = real_localtz.hour 
        minute = real_localtz.minute

        hm_sum = hour + (minute/60.0)

        return (hm_sum>=7 and hm_sum<=10) or (hm_sum>=11.5 and hm_sum<=14) or (hm_sum>=17 and hm_sum<=22)
        
    def stoneOpen(self, real_localtz):
        day_of_week = real_localtz.isoweekday() #mon = 1; sun = 7

        if day_of_week==6 or day_of_week==7:
            return False
        
        return self.luluOpen(real_localtz)

class MainPage(webapp2.RequestHandler):

    def get(self):
        template = JINJA_ENVIRONMENT.get_template('index.html')

        now = datetime.utcnow()
        now = now.replace(tzinfo=pytz.utc)
        real_localtz = datetime.astimezone(now, pytz.timezone('America/New_York'))

        menus = menuUrls(real_localtz)

        lulu = DiningHall("lulu", menus, real_localtz)
        bates = DiningHall("bates", menus, real_localtz)
        pom = DiningHall("pom", menus, real_localtz)
        stone = DiningHall("stone", menus, real_localtz)
        tower = DiningHall("tower", menus, real_localtz)

        date_string = real_localtz.strftime("%A, %B %d")

        template_values = {
            "date_string" : date_string,
            "lulu" : lulu,
            "bates" : bates,
            "pom" : pom,
            "stone" : stone,
            "tower" : tower,
        }

        self.response.write(template.render(template_values))

def menuUrls(real_localtz):
    #dd = "%d" % (real_localtz.day) #for after spring break
    dd = "18"
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
 
class DishHandler(webapp2.RequestHandler):
    def get(self):
        currentEmail = self.request.get("emailaddress")
        submit_template = JINJA_ENVIRONMENT.get_template('submission.html')

        template_values = {}
        template_values["foods"] = []
        foods = [d.dish_name for d in Dish.query(ancestor=DEFAULT_DISH.key).filter(Dish.authors.email == currentEmail).fetch()] #gets dishes who have `user` as someone signed up for alerts
        
        for f in foods:
            template_values["foods"].append(f)
        template_values["emailaddress"] = currentEmail

        self.response.out.write(submit_template.render(template_values))

    def post(self):
        currentEmail = self.request.get("emailaddress")
        user = Author(email=currentEmail)
        logging.info("***------BEGINNING NEW DB ACCESS------***")
        for item in self.request.arguments():
            if item!="emailaddress":
                dish_name_query = Dish.query(ancestor=DEFAULT_DISH.key).filter(Dish.dish_name == item).get() #should only be one Dish entry with "item" name
                #logging.info("DISH=")
                #logging.info(dish_name_query)

                if not dish_name_query: #so dish_name_query hasn't had an alert set up for it yet
                    logging.info("NEW DISH ALERT: "+item)
                    new_dish = Dish(parent=DEFAULT_DISH.key, dish_name=item, authors=[])
                    new_dish.authors.append(user)
                    dish_name_query = new_dish
                else:
                    logging.info("EXISTING DISH ALERT: "+item)
                    old_authors = dish_name_query.authors
                    if not self.__author_found(user.email, old_authors): #to avoid duplicates on the list and thus avoid duplicate email alerts
                        old_authors.append(user)
                    dish_name_query.authors = old_authors

                dish_name_query.put()
        self.redirect('/submission/?emailaddress='+currentEmail)

    def __author_found(self, author_email, author_list):
        for person in author_list:
            if person.email==author_email:
                return True
        return False

class EmailAlertHandler(webapp2.RequestHandler):
    def get(self):
        emailsToSend = {}

        now = datetime.utcnow()
        now = now.replace(tzinfo=pytz.utc)
        tomorrow_localtz = datetime.astimezone(now, pytz.timezone('America/New_York')) - timedelta(days=5) #change after spring break; pretending the 18th is tomorrow

        tomorrowMenuURLS = menuUrls(tomorrow_localtz)

        luluTmrw = DiningHall("lulu", tomorrowMenuURLS, tomorrow_localtz)
        batesTmrw = DiningHall("bates", tomorrowMenuURLS, tomorrow_localtz)
        pomTmrw = DiningHall("pom", tomorrowMenuURLS, tomorrow_localtz)
        stoneTmrw = DiningHall("stone", tomorrowMenuURLS, tomorrow_localtz)
        towerTmrw = DiningHall("tower", tomorrowMenuURLS, tomorrow_localtz)

        allHallTmrw = [luluTmrw, batesTmrw, pomTmrw, stoneTmrw, towerTmrw]

        for dHall in allHallTmrw:
            #logging.info("going through items at "+dHall.name)
            for fI in dHall.food_items:
                fI_query = Dish.query(ancestor=DEFAULT_DISH.key).filter(Dish.dish_name == fI).get()
                
                if fI_query:
                    #logging.info(fI_query.dish_name+" has an alert set up for it by ")
                    pplToAlert = [a.email for a in fI_query.authors]
                    #logging.info(pplToAlert)
                    for personEmail in pplToAlert:
                        if emailsToSend.has_key(personEmail):
                            oldEmailBody = emailsToSend[personEmail]
                            oldEmailBody += "\n"+fI+" will be at "+self.neaten(dHall.name)+" tomorrow"
                            emailsToSend[personEmail] = oldEmailBody
                        else:
                            emailBody = "Hi, "+personEmail+"!\nGood news.\n"+fI+" will be at "+self.neaten(dHall.name)+" tomorrow"
                            emailsToSend[personEmail] = emailBody

        for email in emailsToSend:
            user_ubsub_link = "//wellesley-fresher.appspot.com/unsubscribe/?emailaddress="+email

            emailBody = emailsToSend[email] + "\nUnsubscribe using this link: "+user_ubsub_link[2:]
            emailsToSend[email] = emailBody

            mail.send_mail("Wellesley Fresher App <daily-dish@wellesley-fresher.appspotmail.com>",
                email+"@wellesley.edu",
                "Dining Hall Favs Tomorrow!",
                emailsToSend[email],
                headers = {"List-Unsubscribe": user_ubsub_link}
                )


    def neaten(self, dHallName):
        dHallName = dHallName.title()
        if dHallName == "Pom":
            return "Pomeroy"
        if dHallName == "Stone":
            return "Stone-Davis"
        return dHallName

class LogBounceHandler(webapp2.RequestHandler):
  def post(self):
    post_vars = self.request.POST
    #bounce = BounceNotification(post_vars)
    #logging.info('Bounce notification: %s' + str(bounce.notification))
    username = post_vars["original-to"]
    logging.info("So "+username+" is an invalid email and we should remove all entries for it")
    username = username.split("@wellesley.edu")[0] #domain username

    dishes = [d for d in Dish.query(ancestor=DEFAULT_DISH.key).filter(Dish.authors.email == username).fetch()] #gets Dishes who have `username` as someone signed up for alerts

    for dish in dishes:
        removeAuthorFrmDish(dish, username)

def removeAuthorFrmDish(dish, username):
    authorList = dish.authors
    #logging.info(dish.dish_name+" has the invalid prsn")
    for i in range(len(authorList)):
        if authorList[i].email == username:
            authorList.pop(i) #remove Author with invalid email of username@wellesley.edu from Authors signed up for `dish` alerts
            break
    dish.authors = authorList
    #logging.info(', '.join([a.email for a in dish.authors]))
    dish.put()

class UnsubscribeHandler(webapp2.RequestHandler):
    def get(self):
        currentEmail = self.request.get("emailaddress")
        submit_template = JINJA_ENVIRONMENT.get_template('unsubscribe_page.html')

        template_values = {}
        template_values["foods"] = []
        foods = [d.dish_name for d in Dish.query(ancestor=DEFAULT_DISH.key).filter(Dish.authors.email == currentEmail).fetch()] #gets dishes who have `user` as someone signed up for alerts
        
        for f in foods:
            template_values["foods"].append(f)
        template_values["email"] = currentEmail

        self.response.out.write(submit_template.render(template_values))

    def post(self):
        submit_template = JINJA_ENVIRONMENT.get_template('unsubscribe_success.html')
        template_values = {}

        currentEmail = self.request.get("emailaddress")

        allSubbedItems = [d.dish_name for d in Dish.query(ancestor=DEFAULT_DISH.key).filter(Dish.authors.email == currentEmail).fetch()]
        checkedItems = [chItem for chItem in self.request.arguments() if chItem!="emailaddress"]
        itemsToUnsub = [un for un in allSubbedItems if un not in checkedItems] #inefficient... there are apparently some clever JS tricks

        for item in itemsToUnsub:
            dish = Dish.query(ancestor=DEFAULT_DISH.key).filter(Dish.dish_name == item).get()
            removeAuthorFrmDish(dish, currentEmail)

        self.response.out.write(submit_template.render(template_values))

application = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/submission/', DishHandler),
    ('/tasks/send_alerts', EmailAlertHandler),
    ('/_ah/bounce', LogBounceHandler),
    ('/unsubscribe/', UnsubscribeHandler)
], debug=True)