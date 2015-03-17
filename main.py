import os, logging, string, re
import urllib2
import cgi

import jinja2
import webapp2
from datetime import datetime
from pytz.gae import pytz
from pytz import timezone

from bs4 import BeautifulSoup

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

class MainPage(webapp2.RequestHandler):

    def get(self):
        template = JINJA_ENVIRONMENT.get_template('index.html')

        now = datetime.utcnow()
        now = now.replace(tzinfo=pytz.utc)
        real_localtz = datetime.astimezone(now, pytz.timezone('America/New_York'))

        menus = self.menuUrls(real_localtz)

        lulu = urllib2.urlopen(menus[0]).read()
        bates = urllib2.urlopen(menus[1]).read()
        pom = urllib2.urlopen(menus[2]).read()
        stone = urllib2.urlopen(menus[3]).read()
        tower = urllib2.urlopen(menus[4]).read()

        lulu_soup = BeautifulSoup(lulu).div
        bates_soup = BeautifulSoup(bates).div
        pom_soup = BeautifulSoup(pom).div
        stone_soup = BeautifulSoup(stone).div
        tower_soup = BeautifulSoup(tower).div

        lulu_items = []
        bates_items = []
        pom_items = []
        stone_items = []
        tower_items = []

        for node in lulu_soup.findAll('p'):
            lulu_items.append(''.join(node.findAll(text=True)).encode('utf-8'))
        for node in bates_soup.findAll('p'):
            bates_items.append(''.join(node.findAll(text=True)).encode('utf-8'))
        for node in pom_soup.findAll('p'):
            pom_items.append(''.join(node.findAll(text=True)).encode('utf-8'))
        for node in stone_soup.findAll('p'):
            stone_items.append(''.join(node.findAll(text=True)).encode('utf-8'))
        for node in tower_soup.findAll('p'):
            tower_items.append(''.join(node.findAll(text=True)).encode('utf-8'))

        lulu_items = self.cleanList(lulu_items)
        bates_items = self.cleanList(bates_items)
        pom_items = self.cleanList(pom_items)
        stone_items = self.cleanList(stone_items)
        tower_items = self.cleanList(tower_items)

        lulu_open = self.luluOpen(real_localtz)
        bates_open = pom_open = tower_open = self.bptOpen(real_localtz)
        stone_open = self.stoneOpen(real_localtz)

        date_string = real_localtz.strftime("%A, %B %d")

        template_values = {
            "date_string" : date_string,
            "lulu_items" : lulu_items,
            "lulu_open" : lulu_open,
            "bates_items" : bates_items,
            "bates_open" : bates_open,
            "pom_items" : pom_items,
            "pom_open" : pom_open,
            "stone_items" : stone_items,
            "stone_open" : stone_open,
            "tower_items" : tower_items,
            "tower_open" : tower_open,
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

    def cleanList(self, items):
        keywords = [" if ", "Offered Daily:", "Pure", "pure", "Offered", "Offered daily", "Offered daily:", "Home-style Dinner", "Homestyle Lunch", "Homestyle lunch", "Homestyle Dinner", "Homestyle dinner", "Late Night", "Late Nite", "Late night", "Hot Bar", "hot bar", "Hot bar", "Home-style Lunch", "!supportLineBreakNewLine", "endif", "Continental", "Pizza/Pasta", "Pizza/pasta", "breakfast", "Served", "Brunch", "Dinner", "Daily", "daily", "Lunch", "Breakfast", "served", "continental", "brunch", "lunch", "dinner", "grill", "fusion", "daily", "continental breakfast", "soup", "pizza", "homestyle", "home-style", "home", "style"]
        alphabet = []
        for p in range(len(string.ascii_letters)):
            alphabet.append(string.ascii_letters[p])

        temp = []

        for i in items:
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

        #logging.warning(temp)
        #logging.debug(temp)
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

class Favorite(webapp2.RequestHandler):
    def post(self):
        self.response.write('<html><body>You selected:<pre>')
        self.response.write(cgi.escape(self.request.get('content')))
        self.response.write('</pre></body></html>')

application = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/submit', Favorite),
], debug=True)