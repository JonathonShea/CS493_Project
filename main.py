import datetime

from flask import Flask, render_template, request
from google.cloud import datastore
app = Flask(__name__)

datastore_client = datastore.Client()
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

def store_time(dt):
    entity = datastore.Entity(key=datastore_client.key("visit"))
    entity.update({"timestamp": dt})
    
    datastore_client.put(entity)


def fetch_times(limit):
    query = datastore_client.query(kind="visit")
    query.order = ['-timestamp']

    times = query.fetch(limit=limit)

    return times


@app.route("/" + BUSINESS, methods=['POST'])
def post_business():
    content = request.get_json()
    if not is_business_valid(content):
        return ERROR_MISSING
    new_business = datastore.Entity(key=datastore_client.key(BUSINESS))
    new_business.update({
        'owner_id': content['owner_id'],
        'name': content['name'],
        'street_address': content['street_address'],
        'city': content['city'],
        'state': content['state'],
        'zip_code': content['zip_code']
        })
    datastore_client.put(new_business)
    new_business['id'] = new_business.key.id
    return (new_business, 201)


@app.route("/" + BUSINESS + "/<int:id>", methods=['GET'])
def get_business(id):
    business_key = datastore_client.key(BUSINESS, id)
    business = datastore_client.get(key=business_key)
    if business is None:
        return ERROR_UNKOWN_BUSINESS
    else:
        business['id'] = business.key.id
        return business


@app.route("/" + BUSINESS, methods=['GET'])
def get_businesses():
    query = datastore_client.query(kind=BUSINESS)
    results = list(query.fetch())
    for r in results:
        r['id'] = r.key.id
    return results

@app.route("/" + BUSINESS + "/<int:id>", methods=['PUT'])
def update_business(id):    
    business_key = datastore_client.key(BUSINESS, id)
    business = datastore_client.get(key=business_key)
    if business is None:
        return ERROR_UNKOWN_BUSINESS
    content = request.get_json()
    if not is_business_valid(content):
        return ERROR_MISSING
    business.update({
        owner_id: content[owner_id],
        name: content[name],
        street_address: content[street_address],
        city: content[city],
        state: content[state],
        zip_code: content[zip_code]
        })
    datastore_client.put(business)
    return (business, 200)


@app.route("/" + BUSINESS + "/<int:id>", methods=['DELETE'])
def delete_business(id):
    business_key = datastore_client.key(BUSINESS, id)
    business = datastore_client.get(key=business_key)
    if business is None:
        return ERROR_UNKOWN_BUSINESS
    query = datastore_client.query(kind=REVIEWS)
    query.add_filter(business_id, '=', id)
    results = list(query.fetch())
    for r in results:
        r_key = datastore_client.key(REVIEWS, r.key.id)
        datastore_client.delete(r_key)
    datastore_client.delete(business_key)
    return ('', 204)



@app.route("/" + OWNER + "/<int:id>/" + BUSINESS, methods=['GET'])
def get_owner_businesses(id):
    query = datastore_client.query(kind=BUSINESS)
    query.add_filter(owner_id, '=', id)
    results = list(query.fetch())
    for r in results:
        r['id'] = r.key.id
    return results


@app.route("/" + REVIEWS, methods=['POST'])
def post_review():
    content = request.get_json()
    if not is_review_valid(content):
        return ERROR_MISSING
    business_key = datastore_client.key(BUSINESS, content[business_id])
    business = datastore_client.get(key=business_key)
    if business is None:
        return ERROR_UNKOWN_BUSINESS
    query = datastore_client.query(kind=REVIEWS)
    query.add_filter('user_id' , '=', content['user_id'])
    query.add_filter(business_id, '=', content[business_id])
    result = list(query.fetch())
    if len(result) > 0:
        return ERROR_USER_REVIEW_EXISTS
    review_key = datastore_client.key(REVIEWS)
    new_review = datastore.Entity(key = review_key)
    new_review.update({
        user_id: content[user_id],
        business_id: content[business_id],
        stars: content[stars]
        })
    if review_text in content:
        new_review.update({review_text: content[review_text]})
    datastore_client.put(new_review)
    new_review['id'] = new_review.key.id 
    return (new_review, 201)


@app.route("/" + REVIEWS + "/<int:id>", methods=['GET'])
def get_review(id):
    review_key = datastore_client.key(REVIEWS, id)
    review = datastore_client.get(key=review_key)
    if review is None:
        return ERROR_UNKNOWN_REVIEW
    else:
        review['id'] = id
        return (review, 200)


@app.route("/" + REVIEWS + "/<int:id>", methods=['PUT'])
def update_review(id):
    review_key = datastore_client.key(REVIEWS, id)
    review = datastore_client.get(key=review_key)
    if review is None:
        return ERROR_UNKNOWN_REVIEW
    content = request.get_json()
    if stars not in content: 
        return ERROR_MISSING
    review.update({stars: content[stars]})
    if review_text in content:
        review.update({review_text: content[review_text]})
    datastore_client.put(review)
    return (review, 200)




@app.route("/" + REVIEWS + "/<int:id>", methods=['DELETE'])
def delete_review(id):
    review_key= datastore_client.key(REVIEWS, id)
    review = datastore_client.get(key=review_key)
    if review is None:
        return ERROR_UNKNOWN_REVIEW
    datastore_client.delete(review_key)
    return ('', 204)


@app.route("/" + USERS + "/<int:id>/" + REVIEWS, methods=['GET'])
def get_user_reviews(id):
    query = datastore_client.query(kind=REVIEWS)
    query.add_filter(user_id, '=', id)
    results = list(query.fetch())
    for r in results:
        r['id'] = r.key.id
    return (results, 200)



@app.route("/")
def root():
    # Store the current acces time in Datastore.
    store_time(datetime.datetime.now(tz=datetime.timezone.utc))

    # Fetch the msot recent 10 access times from Datastore. 
    times = fetch_times(10)
    
    return render_template("index.html", times=times)


@app.route('/lodgings', methods=['POST']) 
def post_lodgings():
    content = request.get_json()
    new_key = datastore_client.key(LODGINGS)
    new_lodging = datastore.Entity(key=new_key)
    new_lodging.update({
        'name': content['name'],
        'description': content['description'],
        'price': content['price']
        })
    datastore_client.put(new_lodging)
    new_lodging['id'] = new_lodging.key.id
    return (new_lodging, 201)


@app.route('/lodgings',methods=['GET'])
def get_lodgings():
    query = datastore_client.query(kind=LODGINGS) 
    results = list(query.fetch())
    for r in results:
        r['id'] = r.key.id
    return results 


@app.route('/lodgings/<int:id>',methods=['GET'])
def get_lodging(id):
    lodging_key = datastore_client.key(LODGINGS, id)
    lodging = datastore_client.get(key=lodging_key)
    if lodging is None:
        return {"Error": "No lodging with this id"}, 404
    else:
        lodging['id'] = id 
        return lodging 



if __name__ == "__main__":
    # This is used when running locally only. When deploying to Google App
    # Engine, a webserver process such as Gunicorn will serve the app. This
    # can be configured by adding an `entrypoint` to app.yaml.
    # Flask's development server will automatically serve static files in
    # the "static" directory. See:
    # http://flask.pocoo.org/docs/1.0/quickstart/#static-files. Once deployed,
    # App Engine itself will serve those files as configured in app.yaml.
    app.run(host="127.0.0.1", port=8080, debug=True)
