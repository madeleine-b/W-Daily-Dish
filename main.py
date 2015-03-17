import os, logging, string, re
import urllib2
import cgi

import jinja2
import webapp2
from datetime import datetime
from pytz.gae import pytz
from pytz import timezone

from google.appengine.ext import ndb

from bs4 import BeautifulSoup

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

class DiningHall:

    def __init__(self, hall_name, menus, local_tz):
        if hall_name == "lulu":
            self.food_items=[] 
            self.food_items = self.getFoodItems(menus[0])
            self.isOpen = self.luluOpen(local_tz)
        elif hall_name == "bates":
            self.food_items=[]
            self.food_items = self.getFoodItems(menus[1])
            self.isOpen = self.bptOpen(local_tz)
        elif hall_name == "pom":
            self.food_items=[]
            self.food_items = self.getFoodItems(menus[2])
            self.isOpen = self.bptOpen(local_tz)
        elif hall_name == "stone":
            self.food_items=[]
            self.food_items = self.getFoodItems(menus[3])
            self.isOpen = self.stoneOpen(local_tz)
        elif hall_name == "tower":
            self.food_items=[]
            self.food_items = self.getFoodItems(menus[4])
            self.isOpen = self.bptOpen(local_tz)
        else:
            logging.debug("INVALID DINING HALL")
            self.food_items=[]
            self.food_items.append("INVALID DINING HALL")

    def getFoodItems(self, hallUrl):
        hall = urllib2.urlopen(hallUrl).read()
        hall_soup = BeautifulSoup(hall).div

        for node in hall_soup.findAll('p'):
            self.food_items.append(''.join(node.findAll(text=True)).encode('utf-8'))

        return self.cleanList()

    def cleanList(self):
        keywords = [" if ", "Offered Daily:", "Pure", "pure", "Offered", "Offered daily", "Offered daily:", "Home-style Dinner", "Homestyle Lunch", "Homestyle lunch", "Homestyle Dinner", "Homestyle dinner", "Late Night", "Late Nite", "Late night", "Hot Bar", "hot bar", "Hot bar", "Home-style Lunch", "!supportLineBreakNewLine", "endif", "Continental", "Pizza/Pasta", "Pizza/pasta", "breakfast", "Served", "Brunch", "Dinner", "Daily", "daily", "Lunch", "Breakfast", "served", "continental", "brunch", "lunch", "dinner", "grill", "fusion", "daily", "continental breakfast", "soup", "pizza", "homestyle", "home-style", "home", "style"]
        alphabet = []
        for p in range(len(string.ascii_letters)):
            alphabet.append(string.ascii_letters[p])

        temp = []

        for i in self.food_items:
            i = i.replace(b'\r\n', ' ').replace(b'\xc2\xa0', ' ').replace(b'\xe2\x80\x99', '\'').replace(b'\xc2\x92', '\'').replace(b'\x26', '&')
            i = re.sub("[\(\[].*?[\)\]]", "", i) #removes stuff between parentheses and brackets
            i = ' '.join(i.split()) #removes more than one space between words
            i = i.replace(" and", ',').replace(b'\x2D', '').replace("or ", ',') #sometimes the and-replacement is tricky

            for k in keywords:
                i = i.replace(k, '')
            
            i = "".join([x if ord(x) < 128 else '?' for x in i])

            i = i.strip()

            pos_list = i.split(",")
            for p in pos_list:
                p = p.strip()
                if p.lower() not in keywords and len(p)>1 and p[0] in alphabet:
                    temp.append(p) 

            pos_list = i.split(";")
            if len(pos_list) > 1:
                temp.pop() #means we found a list separated by semi-colons and don't want the original list to be added as one item
                for p in pos_list:
                    p = p.strip()
                    if p not in temp and p.lower() not in keywords and len(p)>1 and p[0] in alphabet:
                        temp.append(p) 

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

        menus = self.menuUrls(real_localtz)

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

    def menuUrls(self, real_localtz):
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


class Favorite(webapp2.RequestHandler):
    def post(self):
        self.response.write('<html><body>You selected:<pre>')
        self.response.write(cgi.escape(self.request.get('content')))
        self.response.write('</pre></body></html>')

application = webapp2.WSGIApplication([
    ('/', MainPage),
    ('submit', Favorite),
], debug=True)