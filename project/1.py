
from flask import Flask , request, redirect , render_template
from sqlalchemy import create_engine , Table, Integer , String ,MetaData , Column

app = Flask(__name__)

engine = create_engine('mysql+pymysql://root:1234@localhost/okay')
meta = MetaData()
user = Table (
        'user' ,meta,
        Column('id',Integer,primary_key=True),
        Column('name',String(50))
    )
meta.create_all(engine)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit',methods=['POST'])
def submit():
    id = int(request.form.get('id'))
    name = request.form.get('name') 
    with engine.connect() as conn:
        conn.execute(user.insert().values(id=id,name=name))
        conn.commit()
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=5000,debug=True)

    