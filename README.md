Name: Udacity Project 4

Description: App Engine application for the Udacity training course.

----

# Application Setup


### 1. Products
- [App Engine][1]

### 2. Language
- [Python][2]

### 3. APIs
- [Google Cloud Endpoints][3]

### 4. Setup Instructions

1. Clone the [conference application repository][7].
2. Update the value of `application` in `app.yaml` to the app ID you
   have registered in the App Engine admin console and would like to use to host
   your instance of this sample.
3. Update the values at the top of `settings.py` to
   reflect the respective client IDs you have registered in the
   [Developer Console][4].
4. Update the value of CLIENT_ID in `static/js/app.js` to the Web client ID
5. (Optional) Mark the configuration files as unchanged as follows:
   `$ git update-index --assume-unchanged app.yaml settings.py static/js/app.js`
6. Run the app with the terminal command `python conference.py`, and ensure it's running by visiting your local server's address (by default [localhost:8080][5].)
7. (Optional) Generate your client library(ies) with [the endpoints tool][6].
8. Deploy your application.

[1]: https://developers.google.com/appengine
[2]: http://python.org
[3]: https://developers.google.com/appengine/docs/python/endpoints/
[4]: https://console.developers.google.com/
[5]: https://localhost:8080/
[6]: https://developers.google.com/appengine/docs/python/endpoints/endpoints_tool
[7]: https://github.com/silveruby/udacity-full-stack/tree/master/P4

----

# Design choices and responses


### Task 1: Add Sessions to a Conference


In models.py, Session, SessionForm and SessionForms classes are defined. Session class is a Datastore model; SessionForm and SessionForms are ProtoRPC models. 

Session class have the following properties and data types:

    name - string 
    highlights - string
    speaker - string
    duration - time
    typeOfSession - string (array)
    date - date
    startTime - time
    
Name, highlights, speaker are defined as string data type. typOfSession is defined as repeated string data type so user can enter multiple types of sessions. 

Both duration (**in minutes**) and startTime (**in HH:MM format**) are time-specific, thus both is definied as time data type. date (**in %Y-%m-%d format**) has date data type.

Conference is an ancestor/parent of Session. In conference.py, createSession calls an utility function _createSessionObject to create a session. The function initializes a session object and assisgns conference key as its parent. 

Speaker is defined as string date type for both Session and SessionForm classes. 

----

### Task 2: Add Sessions to User Wishlist

*addSessionToWishlist(SessionKey)* 

You'll need to identify the session that you want to add to the wishlist. Session key is the url safe entity key of a session. You can use query getAllSessions() to obtain list of session keys. 

*getSessionsInWishlist()*

----

### Task 3: Work on indexes and queries

#### Two additional queries

*getAllSessions()* - Return all sessions

*getPastSessions()* - Return all past conferences before today


#### Query for all non-workshop sessions before 7 pm

Non-workshop sessions is filtered by type, and sessions before 7pm is filtered by startTime. Query restriction for Datastore states that an inequality filter can be applied to at most one property. 

To implement this endpoint, we can query by session type first and then filter the result by start time.

----

## Task 4: Add a Task

Implementation steps for featured speaker

1. **Add task** - Check for featured speaker when user adds a new session. If there's featured speaker, then add set_featured_speaker to task queue. 
2. **Define handler** - SetFeaturedSpeakerHandler is implemented as the handler for set_featured_speaker, and it adds speaker to memecache. 
3. **Define endpoint** - getFeaturedSpeaker is the endopoint for getting the latest featured speaker from memecache. 

