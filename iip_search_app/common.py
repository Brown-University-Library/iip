# -*- coding: utf-8 -*-

import logging, pprint, random, re
import solr
from iip_search_app import settings_app

log = logging.getLogger(__name__)


def facetResults( facet ):
    """ Returns dict of { facet_value_a: count_of_facet_value_a_entries }. """
    try:
        s = solr.SolrConnection( settings_app.SOLR_URL )
        q = s.select( u'*:*', **{u'facet':u'true',u'facet.field':facet} )
        facet_count_dict =q.facet_counts[u'facet_fields'][facet]
        return facet_count_dict
    except Exception as e:
        log.error( u'in common.facetResults(); exception, %s' % unicode(repr(e)) )


def fetchBiblio( q_results, target ):
    """ Takes a solr.core.Result and a target-string,
            does a biblio solr lookup on each one,
            returns a list of biblio key-value dicts.
        Returns a list of dicts (usually 1 dict) of biblio key-value data.
        Called by views._prepare_viewinscr_get_data() """
    assert type(q_results) == solr.core.Results, type(q_results)
    assert type(target) == str, type(target)
    for r in q_results:
        try:
            biblios = _get_biblio_results( r, target )
        except Exception as e:
            log.error( u'in common.fetchBiblio(); id, %s; exception, %s' % (u'n/a', unicode(repr(e))) )
            biblios = []
    return biblios

def _get_biblio_results( r, target ):
    """ Takes a single solr.core.Result entry and a target-string,
            does a biblio solr lookup, and
            returns a list of biblio key-value dicts.
        Called by fetchBiblio() """
    b = solr.SolrConnection( settings_app.BIBSOLR_URL )
    biblios = []
    for t in r[target]:
        w = dict( (n,v) for n,v in (t.split('=') for t in t.split('|') ) )
        u_query_string = u'biblioId:%s' % w['bibl']
        bq = b.query( u_query_string )
        for bqry in bq:
            bqry['nType'] = w['nType']
            bqry['n'] = w['n']
            biblios.append(bqry)
    return biblios


def get_log_identifier( request_session=None ):
    """ Returns a log_identifier unicode_string.
        Sets it in the request session if necessary. """
    log_id = unicode( random.randint(1000,9999) )
    if request_session == None:  # cron script writing to log
        pass
    else:
        if u'log_identifier' in request_session:
            log_id = request_session[u'log_identifier']
        else:
            request_session[u'log_identifier'] = log_id
    return log_id


def queryCleanup(qstring):
    qstring = qstring.replace('(', '')
    qstring = qstring.replace(')', '')
    qstring = qstring.replace('"', '')
    qstring = qstring.replace('_', ' ')
    qstring = re.sub(r'notBefore\:\[(-?\d*) TO 10000\]', r'dates after \1', qstring)
    qstring = re.sub(r'notAfter\:\[-10000 TO (-?\d*)]', r'dates before \1', qstring)
    qstring = re.sub(r' -(\d+)', r' \1 BCE', qstring)
    qstring = re.sub(r' (\d+)\b(?!\sBCE)', r' \1 CE', qstring)
    return qstring


def paginateRequest( qstring, resultsPage, log_id):
    """ Executes solr query on qstring and returns solr.py paginator object, and paginator.page object for given page, and facet-count dict.
        Called by: (views.iip_results()) views._get_POST_context() and views._get_ajax_unistring(). """
    log.debug( u'in common.paginateRequest(); qstring, %s; resultsPage, %s' % (qstring, resultsPage) )
    ( s, q ) = _run_paginator_main_query( qstring, log_id )             # gets solr object and query object
    fq = _run_paginator_facet_query( s, qstring, log_id )               # gets facet-query object
    ( p, pg ) = _run_paginator_page_query( q, resultsPage, log_id )     # gets paginator object and paginator-page object
    f = _run_paginator_facet_counts( fq )                               # gets facet-counts dict
    try:
        dispQstring = queryCleanup(qstring.encode('utf-8'))
        return {'pages': p, 'iipResult': pg, 'qstring':qstring, 'resultsPage': resultsPage, 'facets':f, 'dispQstring': dispQstring}
    except Exception as e:
        log.error( u'in common.paginateRequest(); id, %s; exception, %s' % (log_id, unicode(repr(e))) )
        return False

def _run_paginator_main_query( qstring, log_id ):
    """ Performs a lookup on the query-string; returns solr object and query object.
        Called by paginateRequest()."""
    s = solr.SolrConnection( settings_app.SOLR_URL )
    args = {'rows':25}
    try:
        q = s.query((qstring.encode('utf-8')),**args)
        log.debug( u'in common._run_paginator_main_query(); id, %s; q created via try' % log_id )
    except Exception as e1:
        q = s.query('*:*', **args)
        log.debug( u'in common._run_paginator_main_query(); id, %s; exception, %s; q created via except' % (log_id, unicode(repr(e1))) )
    return ( s, q )

def _run_paginator_facet_query( s, qstring, log_id ):
    """ Performs a facet-lookup for the query-string; returns facet-query object.
        Called by paginateRequest()."""
    args = {'rows':25}
    try:
        fq = s.query((qstring.encode('utf-8')),facet='true', facet_field=['region','city','type','physical_type','language','religion'],**args)
    except:
        fq = s.query('*:*',facet='true', facet_field=['region','city','type','physical_type','language','religion'],**args)
    log.debug( u'in common._run_paginator_facet_query(); id, %s; fq is, `%s`; fq.__dict__ is, `%s`' % (log_id, fq, fq.__dict__) )
    return fq

def _run_paginator_page_query( q, resultsPage, log_id ):
    """ Instantiates a paginator object and, from query-results, creates a paginator.page object.
        Called by paginateRequest(). """
    p = solr.SolrPaginator(q, 25)
    try:
        pg = p.page(resultsPage)
    except Exception as e:
        pg = ''
    log.debug( u'in common._run_paginator_page_query(); id, %s; pg is, `%s`; pg.__dict__ is, `%s`' % (log_id, pg, pg.__dict__) )
    return ( p, pg )

def _run_paginator_facet_counts( fq ):
    """ Returns facet_count dict from the facet-query object.
        Called by paginateRequest(). """
    try:
        f = fq.facet_counts['facet_fields']
    except:
        f    = ''
    return f


def updateQstring( initial_qstring, session_authz_dict, log_id ):
    """ Adds 'approved' display-status limit to solr query string if user is *not* logged in
          (because if user *is* logged in, display facets are shown explicitly).
        Returns modified_qstring dict.
        Called by: views.iipResults(). """
    if ( (session_authz_dict == None)
         or (not u'authorized' in session_authz_dict)
         or (not session_authz_dict['authorized'] == True) ):
        qstring = u'display_status:(approved) AND ' + initial_qstring
    else:
        qstring = initial_qstring
    return { 'modified_qstring': qstring }
