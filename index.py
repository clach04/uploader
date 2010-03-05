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
    '/password', 'password',
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
#In bytes
MaxSize=(20 * 1024 * 1024) # 20MB
MaxSizeAdmin=0 #0 for Administrators


#Exceptions
class DBEntry():
    pass


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

# Form Validation checks
def checkDupUser(i):
    '''Checks to see if a user with the same name already exists.'''
    results=list(db.select('users', dict(name=i.username), where="name = $name"))

    if len(results) > 0:
        return False
    else:
        return True

def Expired(i):
    '''Checks to see if the account has expired'''
    username = i.username

    result=list(db.select('users', dict(name=username), where="name = $name"))
    #user=result[0]
    
    if len(result) == 1:
        user=result[0]
    else:
        raise DBEntry('Too Many Results!')

    expire=user.get('exprdate')
    usertype=user.get('usertype')

    # Administrator accounts should never expire!
    if usertype == 'admin':
        return True

    expdb=datetime.strptime(expire, '%Y-%m-%d %H:%M:%S')
    now=datetime.now()
    
    if now.date() < expdb.date():
        return True
    else:
        return False


#Multiple funciton because login need i.username where the change password needs session.username
def checkLoginPasswd(i):
    '''Checks password to see if the password entered is valid.'''
    username=i.username
    password=i.password
    return checkpassword(username,password)

def checkChangePasswd(i):
    username=session.username
    password=i.password
    return checkpassword(username,password)

def checkpassword(username,password):
    typed_password = crypt.crypt(password, 'td') #Encrypted Typed Password
    user=list(db.select('users', dict(name=username), where="name = $name"))
    if len(user) == 1:
        user=user[0]
    else:
        raise DBEntry('Too Many!')
    db_password=user.get('password') #Encrypted Password in Database
    return typed_password == db_password

# Database lookups + writes
def getUserInfo(user):
    '''Return User Info: Username, Credits, Expiration, Type'''

    lookup=list(db.select('users', dict(name=user), where="name = $name"))
    
    if len(lookup) != 1:
        raise DuplicateDBEntry() #I doubt this is the right error to raise...

    name=lookup[0].get('name')
    credits=lookup[0].get('credits')
    exprdate=lookup[0].get('exprdate')
    usertype=lookup[0].get('usertype')

    return [name, credits, exprdate, usertype]


# Misc Functions ATM

def removeCredit(usedCredit):
    #Ignore credit removal if user is an admin
    if session.usertype=='admin': return

    credits = session.credits - usedCredit

    db.query("UPDATE users SET credits=$c WHERE name=$name", vars=dict(c=credits, name=session.username)) 
    session.credits=credits #Updates session.credits

    return

# The following two Decorators verify user access level
def require_auth(func):
    def wrapper(*args, **kwargs):
        if not session.login:
            return render.error('userL')
        else:
            return func(*args,**kwargs)
    return wrapper

def require_admin(func):
    def wrapper(*args, **kwargs):
        if not session.login:
            return render.error('userL')
        elif not session.usertype=='admin':
            return render.error('adminL')
        else:
            return func(*args, **kwargs)
    return wrapper

adduser_form = form.Form(
    form.Textbox('username', form.notnull,description="Username:",size='15'),
    form.Password('password', form.notnull, description="Password:",size='15'),
    form.Password('password_again', form.notnull, description="Password (again):",size='15'),
    form.Textbox('credits', form.notnull, form.regexp('^\d+$', 'Must be a digit'), description="Upload Credits:",size='2',value='0'), #Set the default to 0 so the form will validate if it's an admin account
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
        ], description='Expiration Day:', value=str(datetime.now().day+1)
    ),
    form.Dropdown('year', [str(datetime.now().year),str(datetime.now().year+1),str(datetime.now().year+2)], description="Experation Year:", onchange="getDays()", value=str(datetime.now().year)),
    form.Dropdown('uType', ['user','admin'], description="User Type:", value="User:", onchange="isAdmin()"),
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
    form.Password('password', description="Password:"),
    validators = []
)

login_form = form.Form(
    form.Textbox('username', form.notnull,description="Username:"),
    form.Password('password', form.notnull, description="Password:"),
    validators = [
        form.Validator("Incorrect UserName/Password Combo", checkLoginPasswd), 
        form.Validator("Account has expired!!", Expired),
    ]
)

changePass_form = form.Form(
    form.Password('password', form.notnull, description="Old Password:"),
    form.Password('newPass1', form.notnull, description="New Password:"),
    form.Password('newPass2', form.notnull, description="New Password (again):"),
    validators = [
        form.Validator("Wrong Password", checkChangePasswd),
        form.Validator("Passwords didn't match.", lambda i: i.newPass1 == i.newPass2),
    ]
)

class index:
    def GET(self):
        if session.login:
            raise web.seeother('/upload')
        else:
            raise web.seeother('/login')

class login:
    def GET(self):
        if session.login:
            raise web.seeother('/')
        return render.login(login_form)

    def POST(self):
        f = login_form()
       
        if f.validates():
            #Get username, credits, exprdate, and usertype than store into session variables
            name,credits,exprdate,usertype=getUserInfo(f.d.username)
            
            #Session Variables
            session.login = 1
            session.username = name 
            session.credits = credits
            session.exprdate = exprdate
            session.usertype = usertype
            raise web.seeother('/')
        else:
            return render.login(f)

class logout:
    def GET(self):
        session.login=0
        session.kill()
        raise web.seeother('/login')

class manageusers:
    @require_admin
    def GET(self):
        # Displays error messages on page if msg is passed
        i=web.input(msg='')
        msg = i.msg

        # Read DB to get a list of users
        users=list(db.select('users'))

        #Admin, Credits, Expr - special user types
        admin=[]
        nocredits=[]
        expired=[]

        # Go through all the users to see if they are either an admin
        # if their account has expired or if they have ran out of credits 
        for x in users:
            if x.get('usertype') == 'admin':
                admin.append(x)
            else:
                # We don't want users listed in both Expired and No Credits
                # Users who have both expired and have no more credits will be listed as expired
                exprdate=datetime.strptime(x.get('exprdate'), '%Y-%m-%d %H:%M:%S')
                credits=int(x.get('credits'))
                if exprdate < datetime.now():
                    expired.append(x)
                elif credits <= 0:
                    nocredits.append(x)

        # Remove users that are Administrators, have 0 credits, or are expired
        # Remaining users must be valid users
        for invalid in itertools.chain(admin, nocredits, expired):
            users.remove(invalid)

        return render.admin_users(admin, users, nocredits, expired, msg)

    @require_admin
    def POST(self): 
        i=web.input(chk=[])

        #Store all the checked users
        id = i.chk

        if i.form_action == 'Delete':
            # Delete Users
            for x in id:
                db.delete('users', where="id=$id", vars=dict(id=x))
            
            return web.seeother('/admin')
        elif i.form_action == 'Edit':
            #Edit a user
            if len(id) == 1:
                id=str(id[0]) #There is only one user id so clobber id with it
                raise web.seeother('/admin/edit?id='+id)
            else:
                # We can't edit more than one user at a time... Issue a warning
                return web.seeother('/admin?msg='+'Select only one user to edit')
        elif i.form_action == 'Files':
            #List Files
            if len(id) == 1:
                id=str(id[0]) #There is only one user id so clobber id with it
                raise web.seeother('/admin/files?id='+id)
            else:
                #We don't have support to show more than one user's files
                return web.seeother('/admin?msg='+'You can only select one user!')
        elif i.form_action == 'Add':
            #Show Add User Page
            raise web.seeother('/admin/adduser')
        return

class adduser:
    @require_admin
    def GET(self): 
        return render.admin_adduser(adduser_form)

    @require_admin
    def POST(self): 
        f = adduser_form()
        if f.validates():
            # If the form validates store variables locally and insert them into the database 
            username = f.d.username.lower()
            password = crypt.crypt(f.d.password, 'td')
            credits = f.d.credits
            date = datetime(int(f.d.year), int(f.d.month), int(f.d.day))
            userType=f.d.uType

            #Store data into the db
            if userType=='user':
                data = {'name':username,'password':password,'credits':str(credits),'exprdate':str(date),'usertype':str(userType)}
            #Administrator entries credits and exprdate entries are going to be NULL
            elif userType=='admin':
                data = {'name':username,'password':password,'credits':None,'exprdate':None,'usertype':str(userType)}
            
            db.insert('users', **data)
            raise web.seeother('/admin')
        else:
            # If the form does not validate render the form again (this will show errors to the user)
            return render.admin_adduser(f)

class edituser:
    @require_admin
    def GET(self): 
        i=web.input(id='')
        id = i.id
        
        user = list(db.select('users', where="id=$id", vars=dict(id=id)))
        user=user[0]

        username=user.get('name')
   
        # What is there to modify in admin user right now?
        if user.get('usertype')=='admin':
            raise web.seeother('/admin?msg='+'Administrators can\'t be edited!')

        f=edit_form
        
        credits=user.get('credits')
        expr=user.get('exprdate')
        y,m,d=expr.split(' ')[0].split('-')
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
 
        u = list(db.select('users', where="id=$id", vars=dict(id=id)))
        if len(u) == 1:
            user=u[0]
        else:
            raise DBEntry('Too many Entries!')

        username=user.get('name')
        
        if f.validates():
            newExpr=datetime( int(f.d.year), int(f.d.month), int(f.d.day))
            newCredits=str(f.d.credits)
            password=f.d.password


            #Can't edit an admin
            if user.get('usertype') == 'admin':
                raise web.seeother('/admin')

            oldCredits = user.get('credits')
            oldExpr=datetime.strptime(u[0].get('exprdate'), '%Y-%m-%d %H:%M:%S')

            if not oldExpr == newExpr:
                db.update('users', where="id=$id", exprdate=newExpr, vars=dict(id=id))

            if not oldCredits == newCredits:
                db.update('users', where="id=$id", credits=newCredits, vars=dict(id=id) )
            
            #Change Password if one was entered
            if password:
                newPass = crypt.crypt(password, 'td') #Encrypted Typed Password
                db.update('users', where="id=$id", password=newPass, vars=dict(id=id) )
        else:
            #Fill in the form with the values that were submitted
            f.fill({'month':f.d.month, 'day':f.d.day, 'year':f.d.year})
            return render.admin_edituser(f,username)

        raise web.seeother('/admin')

class listfiles:
    @require_admin
    def GET(self):        
        i=web.input(id='')
        id = i.id

        if not id:
            raise web.seeother('/admin')

        u = list(db.select('users', where="id=$id", vars=dict(id=id)))        
        if len(u) == 1:
            user=u[0]
        else:
            raise DBEntry('Too Many Entries')


        username=user.get('name')

        dir=os.path.join(filedir, username)
        # Check to see if a directory exists
        # If exists get a file listing if there are no files, the variable files will still be empty
        if os.path.isdir(dir):
            files=os.listdir(dir) #There should never be subdirectories
        else:
            files=[]

        url = []
        size = []
        if files:
            #Go through all the files and generate their urls
            for x in files:
                url.append(uploaddir+'/'+username+'/'+x)

            #Go through all the files and get their size
            for x in files:
                s=os.path.getsize(os.path.join(filedir,username,x))
                size.append(getSize(s))
        #Merge file names, urls, and sizes together
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

class password:
    @require_auth
    def GET(self):
        return render.password(changePass_form,'')

    @require_auth
    def POST(self):
        f = changePass_form()
        if f.validates():
            username = session.username
            password = crypt.crypt(f.d.newPass1, 'td') #Encrypted Typed Password
            db.update('users', where="name=$username", password=password, vars=dict(username=username))
        else:
            return render.password(f,'')
        return render.password(f, 'Password Changed Successfully')

class upload:
    @require_auth
    def GET(self):     
        if session.usertype=='admin':
            cgi.maxlen = MaxSizeAdmin
        else:
            cgi.maxlen = MaxSize
        return render.upload('')
    
    @require_auth
    def POST(self):
        if session.credits <= 0:
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

