from __future__ import annotations
import datetime
from flask import Flask, render_template, request
from google.cloud import datastore


import logging
import os

import sqlalchemy
from sqlalchemy.exc import IntegrityError
from connect_connector import connect_with_connector

LODGINGS = 'lodgings'
REVIEWS = 'reviews'
BUSINESS = 'businesses'
REVIEW = 'review'
OWNER = 'owners'
USERS = 'users'
ERROR_UNKNOWN_REVIEW = ({"Error": "No review with this review_id exists"}, 404)
ERROR_MISSING = ({"Error": "The request body is missing at least one of the required attributes"}, 400)
ERROR_UNKOWN_BUSINESS = ({"Error": "No business with this business_id exists"}, 404)
ERROR_USER_REVIEW_EXISTS = ({"Error": "You have already submitted a review for this business. You can update your previous review, or delete it and submit a new review"}, 409)
business_id = 'business_id'
stars = 'stars'
user_id = 'user_id'
review_text = 'review_text'
owner_id = 'owner_id'
name = 'name'
street_address = 'street_address'
city = 'city'
state = 'state'
zip_code = 'zip_code'
business_attributes = ('owner_id', 'name', 'street_address', 'city', 'state', 'zip_code')
review_attributes = ('user_id', 'business_id', 'stars')

app = Flask(__name__)

logger = logging.getLogger()

# Sets up connection pool for the app
def init_connection_pool() -> sqlalchemy.engine.base.Engine:
    if os.environ.get('INSTANCE_CONNECTION_NAME'):
        return connect_with_connector()
        
    raise ValueError(
        'Missing database connection type. Please define INSTANCE_CONNECTION_NAME'
    )

# This global variable is declared with a value of `None`
db = None

# Initiates connection to database
def init_db():
    global db
    db = init_connection_pool()

# create 'lodgings' table in database if it does not already exist
def create_table(db: sqlalchemy.engine.base.Engine) -> None:
    with db.connect() as conn:
        conn.execute(
            sqlalchemy.text(
                'CREATE TABLE IF NOT EXISTS businesses '
                '(id SERIAL NOT NULL, ' 
                'owner_id DECIMAL NOT NULL, '
                'name VARCHAR(50) NOT NULL, '
                'street_address VARCHAR(100) NOT NULL, '
                'city VARCHAR(50) NOT NULL, '
                'state VARCHAR(2) NOT NULL, '
                'zip_code DECIMAL NOT NULL, '
                'PRIMARY KEY (id) );'
            )
        )
        conn.execute(
                sqlalchemy.text(
                    'CREATE TABLE IF NOT EXISTS reviews '
                    '(id SERIAL NOT NULL, '
                    'user_id DECIMAL NOT NULL, '
                    'business_id BIGINT UNSIGNED NOT NULL,'
                    'stars DECIMAL NOT NULL check(stars BETWEEN 0 and 5), '
                    'review_text VARCHAR(1000), '
                    'PRIMARY KEY (id), '
                    'CONSTRAINT UC_business UNIQUE (user_id,business_id), '
                    'CONSTRAINT FK_business FOREIGN KEY (business_id) '
                    'REFERENCES businesses(id) '
                    'ON DELETE CASCADE);'
                    )
                )
        conn.commit()



# datastore_client = datastore.Client()


def is_business_valid(business):
    for attr in business_attributes:
        if attr not in business:
            return False
    return True


def is_review_valid(review):
    for attr in review_attributes:
        if attr not in review:
            return False
    return True


@app.route('/' + 'businesses', methods=['POST'])
def post_business():
    content = request.get_json()
    try:
        with db.connect() as conn:
            stmt = sqlalchemy.text(
                'INSERT INTO businesses(owner_id, name, street_address, city, state, zip_code) '
                ' VALUES (:owner_id, :name, :street_address, :city, :state, :zip_code)'
            )
            conn.execute(stmt, parameters={'owner_id': content['owner_id'], 
                                        'name': content['name'], 
                                        'street_address': content['street_address'],
                                        'city': content['city'],
                                        'state': content['state'],
                                        'zip_code': content['zip_code']})
            stmt2 = sqlalchemy.text('SELECT last_insert_id()')
            id = conn.execute(stmt2).scalar()
            conn.commit()

    except Exception as e:
        logger.exception(e)
        return ({'Error': 'The request body is missing at least one of the required attributes'}, 400)

    return ({'id': id,
             'owner_id': content['owner_id'], 
             'name': content['name'],
             'street_address': content['street_address'],
             'city': content['city'],
             'state': content['state'],
             'zip_code': content['zip_code'],
             'self': request.base_url + '/' + str(id)}, 201)

@app.route('/businesses/<int:id>', methods=['GET'])
def get_business(id):
    with db.connect() as conn:
        stmt = sqlalchemy.text(
                'SELECT id, owner_id, name, street_address, city, state, zip_code FROM businesses WHERE id=:id'
                )
        row = conn.execute(stmt, parameters={'id': id}).one_or_none()
        if row is None:
            return ERROR_UNKOWN_BUSINESS 
        else:
            business = row._asdict()
            business['owner_id'] = int(business['owner_id'])
            business['zip_code'] = int(business['zip_code'])
            business['self'] = request.base_url 
            return business


@app.route('/businesses', methods=['GET'])
def get_businesses():
    offset = request.args.get('offset',0)
    limit = request.args.get('limit', 3)
    offset_str = ''
    limit_str = ''
    if offset is not None:
        offset_str = ' offset ' + str(offset)
    if limit is not None:
        limit_str = ' limit ' + str(limit)
    with db.connect() as conn:
        stmt = sqlalchemy.text(
                'SELECT * FROM businesses ORDER BY id' + limit_str + offset_str
                )
        rows = conn.execute(stmt)
        businesses = {'entries':[]}
        for row in rows:
            business = row._asdict()
            business['owner_id'] = int(business['owner_id'])
            business['zip_code'] = int(business['zip_code'])
            business['self'] = request.base_url + '/' + str(business['id'])
            businesses['entries'].append(business)
        businesses['next'] = request.base_url + '?offset=' + str(int(offset) + int(limit)) + '&limit=' + str(limit)
        return businesses


@app.route('/businesses/<int:id>', methods=['DELETE'])
def delete_business(id):
    with db.connect() as conn:
        stmt = sqlalchemy.text(
                'DELETE FROM businesses WHERE id=:id'
                )
        result = conn.execute(stmt, parameters={'id': id})
        conn.commit()
        if result.rowcount == 1:
            return ('',204) 
        else:
            return ERROR_UNKOWN_BUSINESS

@app.route('/businesses/<int:id>', methods=['PUT'])
def edit_business(id):
    content = request.get_json()
    if not is_business_valid(content):
        return ERROR_MISSING
    with db.connect() as conn:
       stmt = sqlalchemy.text(
               'SELECT * FROM businesses WHERE id=:id'
               )
       row = conn.execute(stmt, parameters={'id': id}).one_or_none()
       if row is None:
           return ERROR_UNKOWN_BUSINESS

       stmt = sqlalchemy.text(
               'UPDATE businesses '
               'SET owner_id = :owner_id, name = :name, street_address = :street_address, city = :city, state = :state, zip_code = :zip_code '
               'WHERE id = :id'
               )
        
       conn.execute(stmt, parameters={owner_id: content[owner_id],
                                      name: content[name],
                                      street_address: content[street_address],
                                      city: content[city],
                                      state: content[state],
                                      zip_code: content[zip_code],
                                      'id': id})
       conn.commit()
       return {'id': id,
               owner_id: content[owner_id],
               name: content[name],
               street_address: content[street_address],
               city: content[city],
               state: content[state],
               zip_code: content[zip_code],
               'self': request.base_url}


@app.route('/owners/<int:id>/businesses')
def get_businesses_by_owner(id):

    with db.connect() as conn:
        stmt = sqlalchemy.text(
                'SELECT * FROM businesses WHERE owner_id = :owner_id'
                )

        businesses = []
        rows = conn.execute(stmt, parameters={'owner_id': id})
        for business in rows:
            business = business._asdict()
            business['owner_id'] = int(business['owner_id'])
            business['zip_code'] = int(business['zip_code'])
            business['self'] = request.host_url + 'businesses/' + str(business['id'])
            businesses.append(business)
    return businesses


@app.route('/reviews', methods=['POST'])
def create_review():
    content = request.get_json()
    if not is_review_valid(content):
        return ERROR_MISSING
    review = 'NULL'
    if review_text in content:
        review = content[review_text]
    with db.connect() as conn:
        stmt = sqlalchemy.text(
                'INSERT INTO reviews(user_id, business_id, stars, review_text) '
                'VALUES (:user_id, :business_id, :stars, :review_text)'
                )
        try:
            conn.execute(stmt, parameters={'user_id': content[user_id],
                                       'business_id': content[business_id],
                                       'stars': content['stars'],
                                       'review_text': review})

            stmt2 = sqlalchemy.text('SELECT last_insert_id()')
            id = conn.execute(stmt2).scalar()
            conn.commit()
            results = {'id': id,
                       'user_id': content[user_id],
                       'stars': content[stars],
                       'business_id': content[business_id],
                       'self': request.base_url + '/' + str(id),
                       'business': request.host_url +'businesses/' + str(content['business_id'])}
            if review_text in content:
                results[review_text] = content[review_text]
            else:
                results[review_text] = ''
            return (results, 201)
        except IntegrityError as exc:
            if 'Duplicate entry' in str(exc.orig):
                return ERROR_USER_REVIEW_EXISTS
            else:
                return ERROR_UNKOWN_BUSINESS


@app.route('/' + REVIEWS + '/<int:id>', methods=['GET'])
def get_review(id):
    with db.connect() as conn:
        stmt = sqlalchemy.text(
                'SELECT * FROM reviews WHERE id=:id'
                )
        row = conn.execute(stmt, parameters={'id': id}).one_or_none()
        if row is None:
            return ERROR_UNKNOWN_REVIEW
        review = row._asdict()
        review['user_id'] = int(review['user_id'])
        review['business_id'] = int(review['business_id'])
        review['stars'] = int(review['stars'])
        review['self'] = request.base_url
        review['business'] = request.host_url + 'businesses/' + str(review['business_id'])
    return review


@app.route('/' + REVIEWS + '/<int:id>', methods=['PUT'])
def edit_review(id):
    content = request.get_json()
    if stars not in content:
        return ERROR_MISSING
    with db.connect() as conn:
        stmt = sqlalchemy.text(
                'SELECT * FROM reviews WHERE id=:id'
                )
        row = conn.execute(stmt, parameters={'id':id}).one_or_none()
        if row is None:
            return ERROR_UNKNOWN_REVIEW
        stmt = sqlalchemy.text(
                'UPDATE reviews '
                'SET stars = :stars '
                'WHERE id = :id'
                )
        conn.execute(stmt, parameters={'id':id,
                                       'stars': content['stars']})
        review = row._asdict()
        review['stars'] = content['stars']
        if review_text in content:
            stmt = sqlalchemy.text(
                    'UPDATE reviews '
                    'SET review_text = :review_text '
                    'WHERE id = :id'
                    )
            conn.execute(stmt, parameters={'id':id,
                                           'review_text': content['review_text']})
            review['review_text'] = content['review_text']
        conn.commit()
        review['user_id'] = int(review['user_id'])
        review['business'] = request.host_url + 'businesses/' + str(review['business_id'])
        review['self'] = request.base_url
    return review 


@app.route('/' + REVIEWS +'/<int:id>', methods=['DELETE'])
def delete_review(id):
    with db.connect() as conn:
        stmt = sqlalchemy.text(
                'DELETE FROM reviews WHERE id=:id'
                )
        result = conn.execute(stmt, parameters={'id': id})
        conn.commit()
        if result.rowcount == 1:
            return ('',204)
        else:
            return ERROR_UNKNOWN_REVIEW

@app.route('/users/<int:user_id>/reviews', methods=['GET'])
def get_reviews_for_user(user_id):
    with db.connect() as conn:
        stmt = sqlalchemy.text(
                'SELECT * FROM reviews WHERE user_id=:user_id'
                )
        rows = conn.execute(stmt, parameters={'user_id': user_id})
        reviews = []
        for row in rows:
            review = row._asdict()
            review['stars'] = int(review['stars'])
            review['user_id'] = int(review['user_id'])
            review['business_id'] = int(review['business_id'])
            review['business'] = request.host_url + 'businesses/' + str(review['business_id'])
            review['self'] = request.host_url + 'reviews/' + str(review['id'])
            review['id'] = str(review['id'])
            reviews.append(review)
        return reviews
# def store_time(dt)
#     entity = datastore.Entity(key=datastore_client.key("visit"))
#     entity.update({"timestamp": dt})
    
#     datastore_client.put(entity)


# def fetch_times(limit):
#     query = datastore_client.query(kind="visit")
#     query.order = ['-timestamp']

#     times = query.fetch(limit=limit)

#     return times


# @app.route("/" + BUSINESS, methods=['POST'])
# def post_business():
#     content = request.get_json()
#     if not is_business_valid(content):
#         return ERROR_MISSING
#     new_business = datastore.Entity(key=datastore_client.key(BUSINESS))
#     new_business.update({
#         'owner_id': content['owner_id'],
#         'name': content['name'],
#         'street_address': content['street_address'],
#         'city': content['city'],
#         'state': content['state'],
#         'zip_code': content['zip_code']
#         })
#     datastore_client.put(new_business)
#     new_business['id'] = new_business.key.id
#     return (new_business, 201)


# @app.route("/" + BUSINESS + "/<int:id>", methods=['GET'])
# def get_business(id):
#     business_key = datastore_client.key(BUSINESS, id)
#     business = datastore_client.get(key=business_key)
#     if business is None:
#         return ERROR_UNKOWN_BUSINESS
#     else:
#         business['id'] = business.key.id
#         return business


# @app.route("/" + BUSINESS, methods=['GET'])
# def get_businesses():
#     query = datastore_client.query(kind=BUSINESS)
#     results = list(query.fetch())
#     for r in results:
#         r['id'] = r.key.id
#     return results

# @app.route("/" + BUSINESS + "/<int:id>", methods=['PUT'])
# def update_business(id):    
#     business_key = datastore_client.key(BUSINESS, id)
#     business = datastore_client.get(key=business_key)
#     if business is None:
#         return ERROR_UNKOWN_BUSINESS
#     content = request.get_json()
#     if not is_business_valid(content):
#         return ERROR_MISSING
#     business.update({
#         owner_id: content[owner_id],
#         name: content[name],
#         street_address: content[street_address],
#         city: content[city],
#         state: content[state],
#         zip_code: content[zip_code]
#         })
#     datastore_client.put(business)
#     return (business, 200)


# @app.route("/" + BUSINESS + "/<int:id>", methods=['DELETE'])
# def delete_business(id):
#     business_key = datastore_client.key(BUSINESS, id)
#     business = datastore_client.get(key=business_key)
#     if business is None:
#         return ERROR_UNKOWN_BUSINESS
#     query = datastore_client.query(kind=REVIEWS)
#     query.add_filter(business_id, '=', id)
#     results = list(query.fetch())
#     for r in results:
#         r_key = datastore_client.key(REVIEWS, r.key.id)
#         datastore_client.delete(r_key)
#     datastore_client.delete(business_key)
#     return ('', 204)



# @app.route("/" + OWNER + "/<int:id>/" + BUSINESS, methods=['GET'])
# def get_owner_businesses(id):
#     query = datastore_client.query(kind=BUSINESS)
#     query.add_filter(owner_id, '=', id)
#     results = list(query.fetch())
#     for r in results:
#         r['id'] = r.key.id
#     return results


# @app.route("/" + REVIEWS, methods=['POST'])
# def post_review():
#     content = request.get_json()
#     if not is_review_valid(content):
#         return ERROR_MISSING
#     business_key = datastore_client.key(BUSINESS, content[business_id])
#     business = datastore_client.get(key=business_key)
#     if business is None:
#         return ERROR_UNKOWN_BUSINESS
#     query = datastore_client.query(kind=REVIEWS)
#     query.add_filter('user_id' , '=', content['user_id'])
#     query.add_filter(business_id, '=', content[business_id])
#     result = list(query.fetch())
#     if len(result) > 0:
#         return ERROR_USER_REVIEW_EXISTS
#     review_key = datastore_client.key(REVIEWS)
#     new_review = datastore.Entity(key = review_key)
#     new_review.update({
#         user_id: content[user_id],
#         business_id: content[business_id],
#         stars: content[stars]
#         })
#     if review_text in content:
#         new_review.update({review_text: content[review_text]})
#     datastore_client.put(new_review)
#     new_review['id'] = new_review.key.id 
#     return (new_review, 201)


# @app.route("/" + REVIEWS + "/<int:id>", methods=['GET'])
# def get_review(id):
#     review_key = datastore_client.key(REVIEWS, id)
#     review = datastore_client.get(key=review_key)
#     if review is None:
#         return ERROR_UNKNOWN_REVIEW
#     else:
#         review['id'] = id
#         return (review, 200)


# @app.route("/" + REVIEWS + "/<int:id>", methods=['PUT'])
# def update_review(id):
#     review_key = datastore_client.key(REVIEWS, id)
#     review = datastore_client.get(key=review_key)
#     if review is None:
#         return ERROR_UNKNOWN_REVIEW
#     content = request.get_json()
#     if stars not in content: 
#         return ERROR_MISSING
#     review.update({stars: content[stars]})
#     if review_text in content:
#         review.update({review_text: content[review_text]})
#     datastore_client.put(review)
#     return (review, 200)




# @app.route("/" + REVIEWS + "/<int:id>", methods=['DELETE'])
# def delete_review(id):
#     review_key= datastore_client.key(REVIEWS, id)
#     review = datastore_client.get(key=review_key)
#     if review is None:
#         return ERROR_UNKNOWN_REVIEW
#     datastore_client.delete(review_key)
#     return ('', 204)


# @app.route("/" + USERS + "/<int:id>/" + REVIEWS, methods=['GET'])
# def get_user_reviews(id):
#     query = datastore_client.query(kind=REVIEWS)
#     query.add_filter(user_id, '=', id)
#     results = list(query.fetch())
#     for r in results:
#         r['id'] = r.key.id
#     return (results, 200)


@app.route('/')
def index():
    return 'Please navigate to /businesses to use this API'


# @app.route('/lodgings', methods=['POST']) 
# def post_lodgings():
#     content = request.get_json()
#     new_key = datastore_client.key(LODGINGS)
#     new_lodging = datastore.Entity(key=new_key)
#     new_lodging.update({
#         'name': content['name'],
#         'description': content['description'],
#         'price': content['price']
#         })
#     datastore_client.put(new_lodging)
#     new_lodging['id'] = new_lodging.key.id
#     return (new_lodging, 201)


# @app.route('/lodgings',methods=['GET'])
# def get_lodgings():
#     query = datastore_client.query(kind=LODGINGS) 
#     results = list(query.fetch())
#     for r in results:
#         r['id'] = r.key.id
#     return results 


# @app.route('/lodgings/<int:id>',methods=['GET'])
# def get_lodging(id):
#     lodging_key = datastore_client.key(LODGINGS, id)
#     lodging = datastore_client.get(key=lodging_key)
#     if lodging is None:
#         return {"Error": "No lodging with this id"}, 404
#     else:
#         lodging['id'] = id 
#         return lodging 



if __name__ == "__main__":
    # This is used when running locally only. When deploying to Google App
    # Engine, a webserver process such as Gunicorn will serve the app. This
    # can be configured by adding an `entrypoint` to app.yaml.
    # Flask's development server will automatically serve static files in
    # the "static" directory. See:
    # http://flask.pocoo.org/docs/1.0/quickstart/#static-files. Once deployed,
    # App Engine itself will serve those files as configured in app.yaml.
    init_db()
    create_table(db)
    app.run(host='0.0.0.0', port=8080, debug=True)
