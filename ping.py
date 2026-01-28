import turtle


sc = turtle.Screen()
sc.title("Pong game")
sc.bgcolor("black")
sc.setup(width=1000, height=600)

left = turtle.Turtle()
left.speed(0)
left.shape("square")
left.color("white")
left.shapesize(stretch_wid=6, stretch_len=2)
left.penup()
left.goto(-450, 0)

right = turtle.Turtle()
right.speed(0)
right.shape("square")
right.color("white")
right.shapesize(stretch_wid=6, stretch_len=2)
right.penup()
right.goto(450, 0)

ball = turtle.Turtle()
ball.speed(40)
ball.shape("circle")
ball.color("white")
ball.penup()
ball.goto(0, 0)
ball.dx = 5
ball.dy = -5

left_player = 0
right_player = 0

score = turtle.Turtle()
score.speed(0)
score.color("white")
score.penup()
score.hideturtle()
score.goto(0, 260)
score.write("Left_player : 0 Right_player: 0", align="center", font=("Times New Roman", 24, "bold"))

def paddleaup():
	y = left.ycor()
	y += 20
	left.sety(y)


def paddleadown():
	y = left.ycor()
	y -= 20
	left.sety(y)


def paddlebup():
	y = right.ycor()
	y += 20
	right.sety(y)


def paddlebdown():
	y = right.ycor()
	y -= 20
	right.sety(y)

sc.listen()
sc.onkeypress(paddleaup, "w")
sc.onkeypress(paddleadown, "s")
sc.onkeypress(paddlebup, "Up")
sc.onkeypress(paddlebdown, "Down")


while True:
	sc.update()

	ball.setx(ball.xcor()+ball.dx)
	ball.sety(ball.ycor()+ball.dy)

	if ball.ycor() > 280:
		ball.sety(280)
		ball.dy *= -1

	if ball.ycor() < -280:
		ball.sety(-280)
		ball.dy *= -1

	if ball.xcor() > 500:
		ball.goto(0, 0)
		ball.dy *= -1
		left_player += 1
		score.clear()
		score.write("Left_player : {} Right_player: {}".format(left_player, right_player), align="center", font=("Times New Roman", 24, "bold"))

	if ball.xcor() < -500:
		ball.goto(0, 0)
		ball.dy *= -1
		right_player += 1
		score.clear()
		score.write("Left_player : {} Right_player: {}".format(left_player, right_player), align="center", font=("Times New Roman", 24, "bold"))

	if (ball.xcor() > 400 and ball.xcor() < 450) and (ball.ycor() < right.ycor() + 50 and ball.ycor() > right.ycor() - 50):
		ball.setx(400)
		ball.dx*=-1
		
	if (ball.xcor() < -400 and ball.xcor() > -450) and (ball.ycor()<left.ycor() + 50 and ball.ycor()>left.ycor() - 50):
		ball.setx(-400)
		ball.dx*=-1