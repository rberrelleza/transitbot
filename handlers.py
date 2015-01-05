import json
import logging
import os
import sys

import jinja2
import webapp2
from fiveoneone.agency import Agency
from fiveoneone.route import Route

from tenant import Tenant, TenantStore

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)


class HomeHandler(webapp2.RequestHandler):

    def get(self):
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write('Hello, World!')


class CapabilitiesHandler(webapp2.RequestHandler):
    BASEURL_VAR = "TRANSITBOT_BASEURL"

    def get(self):
        template = JINJA_ENVIRONMENT.get_template('capabilities.json')

        pattern = r'(?i)^r?\\/[\\w:!\\?\\-]+'

        self.response.headers['Content-Type'] = 'application/json'
        self.response.write(template.render(dict(base_url=os.environ[self.BASEURL_VAR], pattern=pattern)))


class WebhookHandler(webapp2.RequestHandler):

    COMMANDS = ["/muni"]
    TOKEN_VAR = "TRANSITBOT_TOKEN"

    def get(self):
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write('Hello, WebhookHandler!')

    def post(self):
        body = json.loads(self.request.body)
        event = body.get("event")
        tenant_id = body.get("oauth_client_id")
        message = body.get("item")["message"]["message"]
        room_id = body.get("item")["room"]["id"]

        tenant = TenantStore.get_tenant(tenant_id)
        response = "Sorry, I didn't understand your command"

        if message.startswith("/muni"):
            message_to_parse = message.lstrip("/muni").lstrip().rstrip()
            pieces = message_to_parse.split(" ", 1)

            if len(pieces) >= 2:
                logging.debug("Searching for {}".format(pieces))

                candidate_route = pieces[0]
                candidate_stop = pieces[1]
                token = os.environ[self.TOKEN_VAR]
                muni_agency = Agency(token, "SF-MUNI", True, "bus")
                routes = muni_agency.routes()

                stops = None

                for route in routes:
                    if route.code == candidate_route:
                        inbound_stops = route.stops(Route.INBOUND)
                        outbound_stops = route.stops(Route.OUTBOUND)
                        stops = inbound_stops + outbound_stops
                        break

                if stops == None:
                    reponse = "Sorry, but I couldn't find route {code} in my records.".format(code=candidate_route)
                else:
                    desired_stop = None
                    for stop in stops:
                        if stop.name == candidate_stop:
                            desired_stop = stop
                            break

                    if desired_stop is None:
                        response = "Sorry, but I couldn't find stop '{name}' in my records for route {route}".format(
                            name=candidate_stop, route=route.code)
                    else:
                        departures = stop.next_departures(route.code)
                        response = "{} will arrive to {} in {} minutes".format(
                            route.code, stop.name, ", ".join([str(t) for t in departures.times]))

        tenant.send_notification(room_id, response)
        self.response.status = 204
        


class InstallableHandler(webapp2.RequestHandler):

    def post(self):
        body = json.loads(self.request.body)
        tenant = TenantStore.create_tenant(body)
        logging.info("Installed {}".format(tenant.tenant_id))
        self.response.status = 204

    def delete(self, tenant_id):
        logging.info("Uninstalling {}".format(tenant_id))
        TenantStore.delete_tenant(tenant_id)
        self.response.status = 204
