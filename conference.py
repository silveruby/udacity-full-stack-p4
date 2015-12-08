#!/usr/bin/env python

"""
conference.py -- Udacity conference server-side Python App Engine API;
    uses Google Cloud Endpoints
"""

import time
import datetime

import endpoints
from protorpc import messages
from protorpc import message_types
from protorpc import remote

from google.appengine.ext import ndb
from google.appengine.api import memcache
from google.appengine.api import taskqueue

from utils import getUserId

from models import StringMessage
from models import Profile
from models import ProfileMiniForm
from models import ProfileForm
from models import TeeShirtSize

from models import Conference
from models import ConferenceForm
from models import ConferenceForms

from models import ConferenceQueryForm
from models import ConferenceQueryForms

from models import Session
from models import SessionForm
from models import SessionForms

from models import BooleanMessage
from models import ConflictException

from settings import WEB_CLIENT_ID

EMAIL_SCOPE = endpoints.EMAIL_SCOPE
API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID
MEMCACHE_ANNOUNCEMENTS_KEY = "RECENT ANNOUNCEMENTS"
MEMCACHE_SPEAKER_KEY = "RECENT SPEAKER"

# - - - Profile objects - - - - - - - - - - - - - - - - - - -

DEFAULTS_CONFERENCE = {
    "city": "Default City",
    "maxAttendees": 0,
    "seatsAvailable": 0,
    "topics": ["Default", "Topic"]
}

DEFAULTS_SESSSION = {
    "name": "Default",
    "highlights": "",
    "speaker": "",
    "duration": datetime.time(0).strftime("%M"),
    "typeOfSession": ["General"],
    "startTime": datetime.time(00, 00).strftime("%H:%M"),
    "date": datetime.datetime.now().strftime("%Y-%m-%d")
}

OPERATORS = {
            'EQ':   '=',
            'GT':   '>',
            'GTEQ': '>=',
            'LT':   '<',
            'LTEQ': '<=',
            'NE':   '!='
            }

FIELDS = {
        'CITY': 'city',
        'TOPIC': 'topics',
        'MONTH': 'month',
        'MAX_ATTENDEES': 'maxAttendees',
        }

CONF_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)

CONF_POST_REQUEST = endpoints.ResourceContainer(
    ConferenceForm,
    websafeConferenceKey=messages.StringField(1),
)

SESS_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)

SESS_POST_REQUEST = endpoints.ResourceContainer(
    SessionForm,
    websafeConferenceKey=messages.StringField(1)
)

SESS_GET_BY_TYPE_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
    type=messages.StringField(2)
)

SESS_GET_BY_SPEAKER_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    speaker=messages.StringField(1)
)

WL_POST_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    sessionKey=messages.StringField(1),
)


@endpoints.api(name='conference',
               version='v1',
               allowed_client_ids=[WEB_CLIENT_ID, API_EXPLORER_CLIENT_ID],
               scopes=[EMAIL_SCOPE])
class ConferenceApi(remote.Service):
    """Conference API v0.1"""

# - - - Announcements - - - - - - - - - - - - - - - - - - - -

    @staticmethod
    def _cacheAnnouncement():
        """Create Announcement & assign to memcache; used by
        memcache cron job & putAnnouncement().
        """

        confs = Conference.query(ndb.AND(
            Conference.seatsAvailable <= 5,
            Conference.seatsAvailable > 0)
        ).fetch(projection=[Conference.name])

        if confs:
            print "We are going to set the announcement"

            # If there are almost sold out conferences,
            # format announcement and set it in memcache
            announcement = '%s %s' % (
                'Last chance to attend! The following conferences '
                'are nearly sold out:',
                ', '.join(conf.name for conf in confs))
            memcache.set(MEMCACHE_ANNOUNCEMENTS_KEY, announcement)

            print "The announcement has been set."
        else:
            print "We are going to delete the announcement from memcache"

            # If there are no sold out conferences,
            # delete the memcache announcements entry
            announcement = ""
            memcache.delete(MEMCACHE_ANNOUNCEMENTS_KEY)

            print "The announcement has been deleted from memcache"

        return announcement

    @endpoints.method(message_types.VoidMessage, StringMessage,
                      http_method='GET', name='getAnnouncement')
    def getAnnouncement(self, request):
        """Return Announcement from memcache."""

        # return an existing announcement from Memcache or an empty string.
        announcement = memcache.get(MEMCACHE_ANNOUNCEMENTS_KEY)
        if not announcement:
            announcement = ""
        return StringMessage(data=announcement)

    @endpoints.method(message_types.VoidMessage, StringMessage,
                      http_method='GET', name='getFeaturedSpeaker')
    def getFeaturedSpeaker(self, request):
        """Return Speaker from memcache."""

        # return an existing announcement from Memcache or an empty string.
        speaker = memcache.get(MEMCACHE_SPEAKER_KEY)

        if not speaker:
            speaker = ""

        return StringMessage(data=speaker)

# - - - Profile objects - - - - - - - - - - - - - - - - - - -
    def _copyProfileToForm(self, prof):
        """Copy relevant fields from Profile to ProfileForm."""
        # copy relevant fields from Profile to ProfileForm
        pf = ProfileForm()
        for field in pf.all_fields():
            if hasattr(prof, field.name):
                # convert t-shirt string to Enum; just copy others
                if field.name == 'teeShirtSize':
                    setattr(pf, field.name, getattr(
                                                    TeeShirtSize,
                                                    getattr(prof, field.name)))
                else:
                    setattr(pf, field.name, getattr(prof, field.name))
        pf.check_initialized()
        return pf

    def _getProfileFromUser(self):
        """Return user Profile from datastore
        creating new one if non-existent."""
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # get Profile from datastore
        user_id = getUserId(user)
        p_key = ndb.Key(Profile, user_id)
        profile = p_key.get()
        # create new Profile if not there
        if not profile:
            profile = Profile(
                key=p_key,
                displayName=user.nickname(),
                mainEmail=user.email(),
                teeShirtSize=str(TeeShirtSize.NOT_SPECIFIED),
            )
            profile.put()

        return profile

    def _doProfile(self, save_request=None):
        """Get user Profile and return to user, possibly updating it first."""
        # get user Profile
        prof = self._getProfileFromUser()

        # if saveProfile(), process user-modifyable fields
        if save_request:
            for field in ('displayName', 'teeShirtSize'):
                if hasattr(save_request, field):
                    val = getattr(save_request, field)
                    if val:
                        setattr(prof, field, str(val))
            prof.put()

        # return ProfileForm
        return self._copyProfileToForm(prof)

    @endpoints.method(message_types.VoidMessage, ProfileForm,
                      path='profile', http_method='GET', name='getProfile')
    def getProfile(self, request):
        """Return user profile."""
        return self._doProfile()

    @endpoints.method(ProfileMiniForm, ProfileForm,
                      path='profile', http_method='POST', name='saveProfile')
    def saveProfile(self, request):
        """Update & return user profile."""
        return self._doProfile(request)

# - - - Conference objects - - - - - - - - - - - - - - - - -
    def _copyConferenceToForm(self, conf, displayName):
        """Copy relevant fields from Conference to ConferenceForm."""
        cf = ConferenceForm()
        for field in cf.all_fields():
            if hasattr(conf, field.name):
                # convert Date to date string; just copy others
                if field.name.endswith('Date'):
                    setattr(cf, field.name, str(getattr(conf, field.name)))
                else:
                    setattr(cf, field.name, getattr(conf, field.name))
            elif field.name == "websafeKey":
                setattr(cf, field.name, conf.key.urlsafe())
        if displayName:
            setattr(cf, 'organizerDisplayName', displayName)
        cf.check_initialized()
        return cf

    def _createConferenceObject(self, request):
        """Create or update Conference object
        returning ConferenceForm/request."""
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        if not request.name:
            raise endpoints.BadRequestException(
                "Conference 'name' field required")

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for
                field in request.all_fields()}
        del data['websafeKey']
        del data['organizerDisplayName']

        # add default values for those missing
        # (both data model & outbound Message)
        for df in DEFAULTS_CONFERENCE:
            if data[df] in (None, []):
                data[df] = DEFAULTS_CONFERENCE[df]
                setattr(request, df, DEFAULTS_CONFERENCE[df])

        # convert dates from strings to Date objects
        # set month based on start_date
        if data['startDate']:
            data['startDate'] = datetime.datetime.strptime(
                                    data['startDate'][:10], "%Y-%m-%d").date()
            data['month'] = data['startDate'].month
        else:
            data['month'] = 0
        if data['endDate']:
            data['endDate'] = datetime.datetime.strptime(
                                    data['endDate'][:10], "%Y-%m-%d").date()

        # set seatsAvailable to be same as maxAttendees on creation
        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
        # generate Profile Key based on user ID and Conference
        # ID based on Profile key get Conference key from ID
        p_key = ndb.Key(Profile, user_id)
        c_id = Conference.allocate_ids(size=1, parent=p_key)[0]
        c_key = ndb.Key(Conference, c_id, parent=p_key)
        data['key'] = c_key
        data['organizerUserId'] = request.organizerUserId = user_id

        # create Conference, send email to organizer confirming
        Conference(**data).put()
        taskqueue.add(
            params={
                'email': user.email(),
                'conferenceInfo': repr(request)},
            url='/tasks/send_confirmation_email'
        )

        return request

    @ndb.transactional()
    def _updateConferenceObject(self, request):
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name)
                for field in request.all_fields()}

        # update existing conference
        # get conference key
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()

        # check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' %
                request.websafeConferenceKey)

        # check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')

        # Not getting all the fields, so don't create a new object; just
        # copy relevant fields from ConferenceForm to Conference object
        for field in request.all_fields():
            data = getattr(request, field.name)
            # only copy fields where we get data
            if data not in (None, []):
                # special handling for dates (convert string to Date)
                if field.name in ('startDate', 'endDate'):
                    data = datetime.strptime(data, "%Y-%m-%d").date()
                    if field.name == 'startDate':
                        conf.month = data.month
                # write to Conference object
                setattr(conf, field.name, data)
        conf.put()
        prof = ndb.Key(Profile, user_id).get()
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    def _getQuery(self, request):
        """Return formatted query from the submitted filters."""
        q = Conference.query()
        inequality_filter, filters = self._formatFilters(request.filters)

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Conference.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Conference.name)

        for filtr in filters:
            if filtr["field"] in ["month", "maxAttendees"]:
                filtr["value"] = int(filtr["value"])
            formatted_query = ndb.query.FilterNode(
                                filtr["field"],
                                filtr["operator"],
                                filtr["value"])
            q = q.filter(formatted_query)
        return q

    def _formatFilters(self, filters):
        """Parse, check validity and format user supplied filters."""
        formatted_filters = []
        inequality_field = None

        for f in filters:
            filtr = {field.name: getattr(f, field.name)
                     for field in f.all_fields()}

            try:
                filtr["field"] = FIELDS[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException(
                            "Filter contains invalid field or operator.")

            # Every operation except "=" is an inequality
            if filtr["operator"] != "=":
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException(
                            "Inequality filter is allowed on only one field.")
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)

    @endpoints.method(ConferenceForm, ConferenceForm, path='conference',
                      http_method='POST', name='createConference')
    def createConference(self, request):
        """Create new conference."""
        return self._createConferenceObject(request)

    @endpoints.method(CONF_POST_REQUEST, ConferenceForm,
                      path='conference/{websafeConferenceKey}',
                      http_method='PUT', name='updateConference')
    def updateConference(self, request):
        """Update conference w/provided fields & return w/updated info."""
        return self._updateConferenceObject(request)

    @endpoints.method(CONF_GET_REQUEST, ConferenceForm,
                      path='conference/{websafeConferenceKey}',
                      http_method='GET', name='getConference')
    def getConference(self, request):
        """Return requested conference (by websafeConferenceKey)."""
        # get Conference object from request; bail if not found
        try:
            conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        except:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' %
                request.websafeConferenceKey)

        prof = conf.key.parent().get()
        # return ConferenceForm
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='getConferencesCreated',
                      http_method='POST', name='getConferencesCreated')
    def getConferencesCreated(self, request):
        """Return conferences created by user."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # make profile key
        p_key = ndb.Key(Profile, getUserId(user))
        # create ancestor query for this user
        conferences = Conference.query(ancestor=p_key)
        # get the user profile and display name
        prof = p_key.get()
        displayName = getattr(prof, 'displayName')
        # return set of ConferenceForm objects per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, displayName)
                   for conf in conferences]
        )

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='filterPlayground',
                      http_method='GET', name='filterPlayground')
    def filterPlayground(self, request):
        q = Conference.query()

        # advanced filter building and usage
        field = "city"
        operator = "="
        value = "London"
        f = ndb.query.FilterNode(field, operator, value)
        q = q.filter(f)

        # TODO
        # add 2 filters:
        # 1: city equals to London
        # 2: topic equals "Medical Innovations"

        field = "topics"
        operation = "="
        value = "Medical Innovations"
        f = ndb.query.FilterNode(field, operator, value)
        q = q.filter(f)

        q = q.order(Conference.maxAttendees)

        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, "") for conf in q]
        )

    @endpoints.method(ConferenceQueryForms, ConferenceForms,
                      path='queryConferences',
                      http_method='POST',
                      name='queryConferences')
    def queryConferences(self, request):
        """Query for conferences."""
        conferences = self._getQuery(request)

        # return individual ConferenceForm object per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, "")
                   for conf in conferences]
        )

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='conferences/attending',
                      http_method='GET', name='getConferencesToAttend')
    def getConferencesToAttend(self, request):
        """Get list of conferences that user has registered for."""

        prof = self._getProfileFromUser()  # get user Profile
        conf_keys = [ndb.Key(urlsafe=wsck)
                     for wsck in prof.conferenceKeysToAttend]
        conferences = ndb.get_multi(conf_keys)

        # get organizers
        organisers = [ndb.Key(Profile, conf.organizerUserId)
                      for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return set of ConferenceForm objects per Conference
        return ConferenceForms(items=[self._copyConferenceToForm(
                                                conf,
                                                names[conf.organizerUserId])
                               for conf in conferences])

# - - - Session objects - - - - - - - - - - - - - - - - -
    # getConferenceSessions(websafeConferenceKey)
    @endpoints.method(SESS_GET_REQUEST, SessionForms,
                      http_method='GET', name='getConferenceSessions')
    def getConferenceSessions(self, request):
        """Given a conference, return all sessions"""

        # check websafeKey exists
        if not request.websafeConferenceKey:
            raise endpoints.BadRequestException(
                    "Conference 'websafeKey' field required")

        # convert websafe key to DataStore key
        c_key = ndb.Key(urlsafe=request.websafeConferenceKey)

        # get sessions with ancestor/parent conference key
        # query by kind with an ancestor filter
        sessions = Session.query(ancestor=c_key)

        # return set of SessionForm objects per Conference
        return SessionForms(items=[self._copySessionToForm(sess)
                            for sess in sessions])

    @endpoints.method(SESS_GET_BY_TYPE_REQUEST, SessionForms,
                      http_method='GET', name='getConferenceSessionsByType')
    def getConferenceSessionsByType(self, request):
        """Given a conference
        return all sessions of a specified type
        (eg lecture, keynote, workshop)"""

        # check websafeKey exists
        if not request.websafeConferenceKey:
            raise endpoints.BadRequestException(
                    "Conference 'websafeKey' field required")

        # convert websafe key to DataStore key
        c_key = ndb.Key(urlsafe=request.websafeConferenceKey)

        # get sessions with ancestor/parent conference key
        # query by kind with ancestor filter
        sessions = Session.query(ancestor=c_key)
        # filter by property: type
        sessions = sessions.filter(Session.typeOfSession == request.type)

        # return set of SessionForm objects per Conference
        return SessionForms(items=[self._copySessionToForm(sess)
                            for sess in sessions])

    @endpoints.method(SESS_GET_BY_SPEAKER_REQUEST, SessionForms,
                      http_method='GET', name='getSessionsBySpeaker')
    def getSessionsBySpeaker(self, request):
        """Given a speaker,
        return all sessions given by this particular speaker,
        across all conferences"""

        # get sessions - query by kind
        sessions = Session.query()
        # filter by property: speaker
        sessions = sessions.filter(Session.speaker == request.speaker)

        # return set of SessionForm objects per Conference
        return SessionForms(items=[self._copySessionToForm(sess)
                            for sess in sessions])

    @endpoints.method(message_types.VoidMessage, SessionForms,
                      http_method='GET', name='getAllSessions')
    def getAllSessions(self, request):
        """Return all sessions"""

        # get sessions - query by kind
        sessions = Session.query()

        # return set of SessionForm objects per Conference
        return SessionForms(items=[self._copySessionToForm(sess)
                            for sess in sessions])

    @endpoints.method(message_types.VoidMessage, SessionForms,
                      http_method='GET', name='getPastSessions')
    def getPastSessions(self, request):
        """Return all past conferences before today"""

        # get curent date as datetime object
        current_date = datetime.datetime.now().date()

        # get sessions - query by kind
        sessions = Session.query()
        # filter by property date
        sessions = sessions.filter(Session.date < current_date)

        # return set of SessionForm objects per Conference
        return SessionForms(items=[self._copySessionToForm(sess)
                            for sess in sessions])

    def _copySessionToForm(self, sess):
        """Copy relevant fields from sessions to SessionsForm."""
        sf = SessionForm()
        s_key = sess.key.urlsafe()
        c_key = ""
        if sess.key.parent():
            c_key = sess.key.parent().urlsafe()
        for field in sf.all_fields():
            if hasattr(sess, field.name):
                # convert Date to date string; just copy others
                if field.name.endswith('date'):
                    # convert Date object to string                    
                    date = str(getattr(sess, field.name))
                    setattr(sf, field.name, date)
                elif field.name.endswith('startTime'):
                    # convert Time object to string
                    time = str(getattr(sess, field.name))
                    setattr(sf, field.name, time)
                elif field.name.endswith('duration'):
                    # convert duration to string
                    duration = str(getattr(sess, field.name))
                    setattr(sf, field.name, duration)
                else:
                    setattr(sf, field.name, getattr(sess, field.name))
            elif field.name == "websafeConferenceKey":
                setattr(sf, field.name, c_key)
            elif field.name == "websafeSessionKey":
                setattr(sf, field.name, s_key)
        sf.check_initialized()
        return sf

    @endpoints.method(SESS_POST_REQUEST, SessionForm,
                      path='conference/{websafeConferenceKey}/session/new',
                      http_method='POST', name='createSession')
    def createSession(self, request):
        """Create session, open only to the organizer of the conference"""
        return self._createSessionObject(request)

    def _createSessionObject(self, request):
        """Create or update Sesssion object, returning SessionForm/request."""

        # make sure websafeKey exists
        if not request.websafeConferenceKey:
            raise endpoints.BadRequestException(
                        "Conference 'websafeKey' field required")

        # get conference key
        c_key = ndb.Key(urlsafe=request.websafeConferenceKey)

        # check that conference object exists
        conf = c_key.get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' %
                request.websafeConferenceKey)

        # check user permission to create session
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')

        # copy SessionForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name)
                for field in request.all_fields()}
        del data['websafeConferenceKey']
        del data['websafeSessionKey']

        # add default values for those missing
        # (both data model & outbound Message)
        for df in DEFAULTS_SESSSION:
            if data[df] in (None, []):
                data[df] = DEFAULTS_SESSSION[df]
                setattr(request, df, DEFAULTS_SESSSION[df])

        # convert strings to Date objects
        if data['date']:
            data['date'] = datetime.datetime.strptime(data['date'][:10],
                                                      "%Y-%m-%d").date()

        # convert strings to Time object for startTime
        if data['startTime']:
            data['startTime'] = datetime.datetime.strptime(data['startTime'],
                                                           "%H:%M").time()
     
        # convert strings to Time object for duation
        if data['duration']:
            duration = datetime.timedelta(minutes=int(data['duration']))
            data['duration'] = (datetime.datetime.min + duration).time()

        # Task queue for fatured speaker
        if data['speaker']:

            sessions = Session.query(ancestor=c_key)
            sessions = sessions.filter(Session.speaker == data['speaker'])

            if sessions.get():
                taskqueue.add(
                    params={'speaker': data['speaker']},               
                    url='/tasks/set_featured_speaker'
                )

        # allocate an id for session
        s_id = Session.allocate_ids(size=1, parent=c_key)[0]
        # create session key and set parent to conference key
        s_key = ndb.Key(Session, s_id, parent=c_key)
        data['key'] = s_key

        # creation of Session & return (modified) SessionForm
        s_key = Session(**data).put()

        return self._copySessionToForm(s_key.get())

# - - - Wishlist - - - - - - - - - - - - - - - - - - - -

    # addSessionToWishlist(SessionKey)
    @endpoints.method(WL_POST_REQUEST, ProfileForm,
                      path='profile/wishlist/add/{sessionKey}',
                      http_method='POST', name='addSessionToWishlist')
    def addSessionToWishlist(self, request):
        """Adds the session to the user's list of sessions
        they are interested in attending"""
        return self._addSessiontoWishlistObject(request)

    @ndb.transactional()
    def _addSessiontoWishlistObject(self, request):
        """"Private method to handle add session to wishlist"""

        # check session exist
        session = ndb.Key(urlsafe=request.sessionKey).get()
        if not session:
            raise endpoints.NotFoundException(
                'No session found with key: %s' % request.sessionKey)

        # get profile
        prof = self._getProfileFromUser()

        # add session key to wishlist
        prof.sessionKeysToWishlist.append(request.sessionKey)
        prof.put()

        return self._copyProfileToForm(prof)

    # deleteSessionInWishlist(SessionKey)
    @endpoints.method(WL_POST_REQUEST, ProfileForm,
                      path='profile/wishlist/delete/{sessionKey}',
                      http_method='POST', name='deleteSessionInWishlist')
    def deleteSessionInWishlist(self, request):
        """Delete the session to the user's list of sessions
        they are interested in attending"""
        return self._deleteSessionInWishlistObject(request)

    @ndb.transactional()
    def _deleteSessionInWishlistObject(self, request):
        """"Private method to handle delete session to wishlist"""

        # check session exist
        session = ndb.Key(urlsafe=request.sessionKey).get()
        if not session:
            raise endpoints.NotFoundException(
                'No session found with key: %s' % request.sessionKey)

        # get profile
        prof = self._getProfileFromUser()

        # delete session key to wishlist
        prof.sessionKeysToWishlist.remove(request.sessionKey)
        prof.put()

        return self._copyProfileToForm(prof)        

    @endpoints.method(message_types.VoidMessage, SessionForms,
                      http_method='POST', name='getSessionsInWishlist')
    def getSessionsInWishlist(self, request):
        """Query for all the sessions in a conference
        that the user is interested in"""

        # get profile
        prof = self._getProfileFromUser()

        # get session datastore objects
        sessions = [ndb.Key(urlsafe=s_key).get()
                    for s_key in prof.sessionKeysToWishlist]

        # return set of SessionForm objects per Conference
        return SessionForms(items=[self._copySessionToForm(sess)
                            for sess in sessions])

# - - - Registration - - - - - - - - - - - - - - - - - - - -

    @ndb.transactional(xg=True)
    def _conferenceRegistration(self, request, reg=True):
        """Register or unregister user for selected conference."""
        retval = None

        # get user Profile
        prof = self._getProfileFromUser()

        # check if conf exists given websafeConfKey
        # get conference; check that it exists
        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # register
        if reg:
            # check if user already registered otherwise add
            if wsck in prof.conferenceKeysToAttend:
                raise ConflictException(
                    "You have already registered for this conference")

            # check if seats avail
            if conf.seatsAvailable <= 0:
                raise ConflictException(
                    "There are no seats available.")

            # register user, take away one seat
            prof.conferenceKeysToAttend.append(wsck)
            conf.seatsAvailable -= 1
            retval = True

        # unregister
        else:
            # check if user already registered
            if wsck in prof.conferenceKeysToAttend:

                # unregister user, add back one seat
                prof.conferenceKeysToAttend.remove(wsck)
                conf.seatsAvailable += 1
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        prof.put()
        conf.put()
        return BooleanMessage(data=retval)

    @endpoints.method(
                    CONF_GET_REQUEST, BooleanMessage,
                    path='conference/{websafeConferenceKey}',
                    http_method='POST', name='registerForConference')
    def registerForConference(self, request):
        """Register user for selected conference."""
        return self._conferenceRegistration(request)


# registers API
api = endpoints.api_server([ConferenceApi])
