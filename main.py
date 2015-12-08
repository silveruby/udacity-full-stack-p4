#!/usr/bin/env python

"""
main.py -- Udacity conference server-side Python App Engine
    HTTP controller handlers for memcache & task queue access

$Id$

created by wesc on 2014 may 24

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'

import webapp2

from google.appengine.api import app_identity
from google.appengine.api import mail
from google.appengine.api import memcache

from conference import ConferenceApi

MEMCACHE_SPEAKER_KEY = "RECENT SPEAKER"

# - - - Confirmation Email - - - - - - - - - - - - - - - - - - - -

class SendConfirmationEmailHandler(webapp2.RequestHandler):
    def post(self):
        """Send email confirming Conference creation."""
        mail.send_mail(
            'noreply@%s.appspotmail.com' % (
                app_identity.get_application_id()),     # from
            self.request.get('email'),                  # to
            'You created a new Conference!',            # subj
            'Hi, you have created a following '         # body
            'conference:\r\n\r\n%s' % self.request.get(
                'conferenceInfo')
        )

# - - - Announcement - - - - - - - - - - - - - - - - - - - -

class SetAnnouncementHandler(webapp2.RequestHandler):
    def get(self):
        """Set Announcement in Memcache."""
        # use _cacheAnnouncement() to set announcement in Memcache
        ConferenceApi._cacheAnnouncement()

# - - - Featured Speaker - - - - - - - - - - - - - - - - - - - -

class SetFeaturedSpeakerHandler(webapp2.RequestHandler):
    def post(self):
        """Set Announcement in Memcache."""

        # add as featured speaker and set it in memcache
        announcement = "Featured speaker: %s" % self.request.get('speaker')
        memcache.set(MEMCACHE_SPEAKER_KEY, announcement)

# - - - Set Application - - - - - - - - - - - - - - - - - - - -
app = webapp2.WSGIApplication([
    ('/crons/set_announcement', SetAnnouncementHandler),
    ('/tasks/set_featured_speaker', SetFeaturedSpeakerHandler),
    ('/tasks/send_confirmation_email', SendConfirmationEmailHandler),
], debug=True)
