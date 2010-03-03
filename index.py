#!/usr/bin/env python

import web
from web import form
import sqlite3
import crypt
import os
import cgi
from datetime import datetime
import sys
import itertools

#Must be disabled, otherwise sessions break!!!
web.config.debug = False

urls = (
    '/', 'index',
    '/upload', 'upload',
    '/login', 'login',
    '/logout', 'logout',
    '/admin/adduser', 'adduser',
    '/admin', 'manageusers',
    '/admin/edit', 'edituser',
    '/admin/files', 'listfiles'
)

app = web.application(urls,globals())

#Session Timeout...
web.config.session_parameters['timeout'] = 900 #Session Time Out - 15 Minutes 
web.config.session_parameters['ignore_expiry'] = False  #Defaults sets to true
web.config.session_parameters['expired_message'] = 'Session Expired... Please reload the page and login in again.' #Error message when session expires

#Initalizes and stores session information in sqlite database
db = web.database(dbn="sqlite", db="app.db")
store = web.session.DBStore(db, 'sessions')
session = web.session.Session(app, store, initializer={'login': 0,'userType':'anonymous'})

#Setup Template Rendering
render = web.template.render('templates/')

web.template.Template.globals['render'] = render
web.template.Template.globals['session'] = session
web.template.Template.globals['datetime'] = datetime
web.template.Template.globals['ctx'] = web.ctx

filedir = '/home/http/pyther.net/uploads' #Physical Path to file uploads on file system
uploaddir = 'http://pyther.net/uploads'   #Web Address to said uploads

# Since there is no good predefined function we are going to do the math ourselves
# We shouldn't need to go into terrabytes... at least not today!
def getSize(bytes):
    '''getSize function. Return B, KB, MB, or GB'''
    bytes=float(bytes)
    KB=bytes/1024

    if KB < 1:
        return str(bytes) + ' B'
    elif KB < 1024:
        return str(round(KB,2)) + ' KB'

    MB=KB/1024

    if MB < 1024:
        return str(round(MB,2)) + ' MB'

    GB=MB/1024
    return str(round(GB,2)) + ' GB'

def checkDupUser(i):
    '''Checks to see if a user with the same name already exists.'''
    myvar = dict(name=i.username) 
    results=list(db.select('users', myvar, where="name = $name"))
 
    if len(results) > 0:
        return False
    else:
        return True

def checkPasswd(i):
    '''Checks password to see if the password entered is valid.'''
    username = i.username
    password = crypt.crypt(i.password, 'td')
    myvar = dict(name=username)
    results=list(db.select('users', myvar, where="name = $name"))
    login_password=results[0].get('password')
 
    return password == login_password

def logged_in():
    '''True/False - User Logged In'''
    if session.login == 1:
        return True
    else:
        return False

def isAdmin():
    '''True/False - User is an Administrator'''
    # If the user is not logged in the user can not be an Administrator
    if not logged_in():
        return False
    if getUserType() == 'admin':
        return True
    else:
        return False

def hasCredit(i):
    username = i.username 
    
    myvar = dict(name=username)
    results=list(db.select('users', myvar, where="name = $name"))
    credits=results[0].get('credits')
    
    #Administrators have unlimited credits
    if isAdmin():
        return True
    elif credits > 0:
        return True
    else:
        return False

# Is the user an administrator or an users
def getUserType():
    username = session.username
    myvar = dict(name=username)
    results=list(db.select('users', myvar, where="name = $name"))
    return results[0].get('usertype')


def Expired(i):
    '''Checks to see if the account has expired'''
    username = i.username
    
    myvar = dict(name=username)
    results=list(db.select('users', myvar, where="name = $name"))
    
    expire=results[0].get('exprdate')
    usertype=results[0].get('usertype')
 
    # Administrator accounts should never expire!
    if usertype == 'admin':
        return True

    expdb=datetime.strptime(expire, '%Y-%m-%d %H:%M:%S')
    now=datetime.now()

    if now.date() < expdb.date():
        return True
    else:
        return False

def getCredits():
    '''Returns number of credits user has''' 
    username=session.username

    myvar = dict(name=username)
    results=list(db.select('users', myvar, where="name = $name"))
    credits=int(results[0].get('credits'))

    session.credits=credits

    return credits

def getExpr():
    username=session.username
 
    myvar = dict(name=username)
    results=list(db.select('users', myvar, where="name = $name"))
    expire=results[0].get('exprdate')

    return expire

def removeCredit(usedCredit):
    #Ignore credit removal if user is an admin
    if isAdmin():
        return

    oldCredits=getCredits() #Updates session.credits and get credits from DB
    credits = oldCredits - usedCredit

    db.query("UPDATE users SET credits=$c WHERE name=$name", vars=dict(c=credits, name=session.username))
    
    session.credits=credits #Updates session.credits
    return

# The following two Decorators verify user access level
def require_auth(func):
    def wrapper(*args, **kwargs):
        if not logged_in():
            return render.error('userL')
        else:
            return func(*args,**kwargs)
    return wrapper

def require_admin(func):
    def wrapper(*args, **kwargs):
        if not isAdmin():
            return render.error('adminL')
        else:
            return func(*args, **kwargs)
    return wrapper

adduser_form = form.Form(
    form.Textbox('username', form.notnull,description="Username:",size='15'),
    form.Password('password', form.notnull, description="Password:",size='15'),
    form.Password('password_again', form.notnull, description="Password (again):",size='15'),
    form.Textbox('credits', form.notnull, form.regexp('^\d+$', 'Must be a digit'), description="Upload Credits:",size='2'),
    form.Dropdown('month',
        [
            ('1', 'Janurary'),
            ('2', 'Feburary'),
            ('3', 'March'),
            ('4', 'April'),
            ('5', 'May'),
            ('6', 'June'),
            ('7', 'July'),
            ('8', 'August'),
            ('9', 'September'),
            ('10', 'October'),
            ('11', 'November'),
            ('12', 'Decemember')
        ],
        onchange="getDays()",
        description='Expiration Month:', value=str(datetime.now().month)
    ),
    form.Dropdown('day', [
            ('1'),('2'),('3'),('4'),('5'),('6'),('7'),('8'),('9'),('10'),
            ('11'),('12'),('13'),('14'),('15'),('16'),('17'),('18'),('19'),('20'),
            ('21'),('22'),('23'),('24'),('25'),('26'),('27'),('28'),('29'),('30'),('31')
        ], description='Expiration Day:', value=str(datetime.now().day)
    ),
    form.Dropdown('year', [str(datetime.now().year),str(datetime.now().year+1),str(datetime.now().year+2)], description="Experation Year:", onchange="getDays()", value=str(datetime.now().year)),
    form.Dropdown('uType', ['user','admin'], description="User Type:", value="User:"),
    validators = [
        form.Validator("Passwords didn't match.", lambda i: i.password == i.password_again),
        form.Validator("Duplicate User.", checkDupUser)
    ]
)


edit_form = form.Form(
    form.Textbox('credits', form.notnull, form.regexp('\d+', 'Must be a digit'), description="Upload Credits:",size='2'),
    form.Dropdown('month',
        [
            ('01', 'Janurary'),
            ('02', 'Feburary'),
            ('03', 'March'),
            ('04', 'April'),
            ('05', 'May'),
            ('06', 'June'),
            ('07', 'July'),
            ('08', 'August'),
            ('09', 'September'),
            ('10', 'October'),
            ('11', 'November'),
            ('12', 'Decemember')
        ],
        onchange="getDays()",
        description='Expiration Month:'
    ),
    form.Dropdown('day', [
            ('01'),('02'),('03'),('04'),('05'),('06'),('07'),('08'),('09'),('10'),
            ('11'),('12'),('13'),('14'),('15'),('16'),('17'),('18'),('19'),('20'),
            ('21'),('22'),('23'),('24'),('25'),('26'),('27'),('28'),('29'),('30'),('31')
        ], description='Expiration Day:'
    ),
    form.Dropdown('year', [str(datetime.now().year),str(datetime.now().year+1),str(datetime.now().year+2)], description="Experation Year:", onchange="getDays()"),
    validators = []
)

login_form = form.Form(
    form.Textbox('username', form.notnull,description="Username:"),
    form.Password('password', form.notnull, description="Password:"),
    validators = [
        form.Validator("Incorrect UserName/Password Combo", checkPasswd), 
        form.Validator("Account has expired!!", Expired),
    ]
)

class index:
    def GET(self):
        if logged_in():
            raise web.seeother('/upload')
        else:
            raise web.seeother('/login')

class login:
    def GET(self):
        if logged_in():
            raise web.seeother('/')
        return render.login(login_form)

    def POST(self):
        f = login_form()
       
        if f.validates():
            session.login = 1
            session.username = f.d.username 
            session.credits = getCredits()
            session.expiration = getExpr().split(' ')[0]
            session.userType = getUserType()
            raise web.seeother('/')
        else:
            return render.login(f)

class logout:
    def GET(self):
        session.login=0
        session.kill()
        raise web.seeother('/login')


class adduser:
    @require_admin
    def GET(self): 
        return render.admin_adduser(adduser_form)

    @require_admin
    def POST(self): 
        f = adduser_form()
        if f.validates():
            username = f.d.username
            password = crypt.crypt(f.d.password, 'td')
            credits=f.d.credits
            date=datetime(int(f.d.year), int(f.d.month), int(f.d.day))
            userType=f.d.uType

            data = {'name':username,'password':password,'credits':str(credits),'exprdate':str(date),'usertype':str(userType)}
            db.insert('users', **data)
            raise web.seeother('/admin')
        else:
            return render.admin_adduser(f)


class manageusers:
    @require_admin
    def GET(self):
        i=web.input(msg='')

        msg = i.msg

        data=list(db.select('users'))

        users = []
        for x in data:
            users.append(x)

        #Admin, Credits, Expr, Normal Users
        admin=[]
        nocredits=[]
        expired=[]

        for x in users: 
            exprdate=datetime.strptime(x.get('exprdate'), '%Y-%m-%d %H:%M:%S')
            credits=int(x.get('credits'))

            if x.get('usertype') == 'admin':
                admin.append(x)
            elif exprdate < datetime.now():
                expired.append(x)
            elif credits <= 0:
                nocredits.append(x)

        for removal in itertools.chain(admin, nocredits, expired):
            users.remove(removal)

        return render.admin_users(admin, users, nocredits, expired, msg)

    @require_admin
    def POST(self): 
        i=web.input(chk=[])

        id = i.chk

        if i.form_action == 'Delete':
            for x in id:
                db.delete('users', where="id=$id", vars=dict(id=x))
            
            return web.seeother('/admin')
        elif i.form_action == 'Edit':
            if len(id) == 1:
                id=str(id[0])
                raise web.seeother('/admin/edit?id='+id)
            else:
                return web.seeother('/admin?msg='+'Select only one user to edit')
        elif i.form_action == 'Files':
            if len(id) == 1:
                id=str(id[0])
                raise web.seeother('/admin/files?id='+id)
            else:
                return web.seeother('/admin?msg='+'You can only select one user!')
        elif i.form_action == 'Add':
            raise web.seeother('/admin/adduser')
        return

class edituser:
    @require_admin
    def GET(self): 
        i=web.input(id='')
        id = i.id
        
        u = list(db.select('users', where="id=$id", vars=dict(id=id)))
        
        username=u[0].get('name')
        credits=u[0].get('credits')
        expr=u[0].get('exprdate')
        y,m,d=expr.split(' ')[0].split('-')

        f=edit_form
        f.fill({'credits':credits, 'month':m, 'day':d, 'year':y})

        return render.admin_edituser(f, username)

    @require_admin
    def POST(self): 
        f = edit_form()
        
        i = web.input(id='')
        id = i.id

        #If no id is given...
        if not id:
            raise web.seeother('/admin')
 
        if f.validates():
            newExpr=datetime( int(f.d.year), int(f.d.month), int(f.d.day))
            newCredits=str(f.d.credits)
             
            u = list(db.select('users', where="id=$id", vars=dict(id=id)))
            
            #Can't edit an admin
            if u[0].get('usertype') == 'admin':
                raise web.seeother('/admin')

            oldCredits = u[0].get('credits')
            oldExpr=datetime.strptime(u[0].get('exprdate'), '%Y-%m-%d %H:%M:%S')

            if not oldExpr == newExpr:
                db.update('users', where="id=$id", exprdate=newExpr, vars=dict(id=id))

            if not oldCredits == newCredits:
                db.update('users', where="id=$id", credits=newCredits, vars=dict(id=id) )
        else:
            return render.admin_edituser(f,'')


        raise web.seeother('/admin')

class listfiles:
    @require_admin
    def GET(self):        
        i=web.input(id='')
        id = i.id

        if not id:
            raise web.seeother('/admin')

        u = list(db.select('users', where="id=$id", vars=dict(id=id)))        
        username=u[0].get('name')

        dir=os.path.join(filedir, username)

        try:
            files=os.listdir(dir) #There should never be subdirectories
        except OSError:
            files=[]

        url = []
        size = []
        if files:
            for x in files:
                url.append(uploaddir+'/'+username+'/'+x)

            for x in files:
                s=os.path.getsize(os.path.join(filedir,username,x))
                size.append(getSize(s))

        f = zip(files, url, size)

        return render.admin_files(f, username)

    @require_admin
    def POST(self): 
        i=web.input(chk=[])

        files = i.chk
        username = i.username

        for x in files:
            os.remove(os.path.join(filedir, username, x))

        u = list(db.select('users', where="name=$username", vars=dict(username=username)))        
        id=u[0].get('id')
        
        raise web.seeother('/admin/files?id='+str(id))

class upload:
    @require_auth
    def GET(self):
        if not logged_in():
            raise web.seeother('/login') 
    
        
        if isAdmin():
            cgi.maxlen = 0
        else:
            cgi.maxlen = 20 * 1024 * 1024 # 20MB
        return render.upload('')
    
    @require_auth
    def POST(self):
        if not logged_in():
            raise web.seeother('/login')
        elif getCredits() <= 0:
            return render.upload('No more upload Credits!')
        
        try:
            x=web.input(upfile={})
        except ValueError:
            return render.upload('File too large! Max Upload Size: ' + cgi.maxlen)
        
        if not x.upfile.filename:
            return render.upload('You did not select a file.')

        if 'upfile' in x:
            filepath=x.upfile.filename.replace('\\','/')
            filename=filepath.split('/')[-1]

            path = os.path.join(filedir, session.username)
            newFile = os.path.join(path, filename)
            
            #Creates folder for specific user
            if not os.path.exists(path):
                os.mkdir(path)

            fout = open(newFile,'w')
            #Upload Credit Used
            removeCredit(1) #1 Credit per upload; this might change though
            fout.write(x.upfile.file.read())
            fout.close()

            os.chmod(newFile, 0644) #Just to be on the safe side
    
            url=uploaddir+'/'+session.username+"/"+filename

        return render.upResult(filename, url)
        
if __name__ == "__main__": app.run()

