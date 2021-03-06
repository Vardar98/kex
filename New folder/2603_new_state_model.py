import matplotlib.pyplot as plt
import numpy as np
import math
import cvxpy as cp
import scipy as sp
from scipy import sparse

# Vehicle parameters
PARA = 1  # Use to minimize the vehicle parameters
LENGTH = 4.5 / PARA  # [m]
WIDTH = 2.0 / PARA  # [m]
BACKTOWHEEL = 1.0 / PARA  # [m]
WHEEL_LEN = 0.3 / PARA  # [m]
WHEEL_WIDTH = 0.2 / PARA  # [m]5
TREAD = 0.7 / PARA  # [m]
WB = 2.5 / PARA  # [m]

# Road length
ROAD_LENGTH = 400 # [m]

# Initial acceleration
U_INIT = 0.0 # m/s^2

INIT_DIST = 10.0    # Initial distance between the cars

# Initial velocity
V_INIT = 100.0 / 3.6 # 100km/h -> 100/3.6 m/s

# Prediction horizon
PREDICTION_HORIZON = 30

# Constriants
SAFETY_DISTANCE = 1. + LENGTH
MAX_ACCELERATION = 5  # 5 m/s^2
MIN_ACCELERATION = -10 # 10 m/s^2 decleration
MAX_VEL = 120/3.6 # m/s
MIN_VEL = 80/3.6 # m/s

# Max time
MAX_TIME = 5  # [s]
# Time step
DT = 0.3  # [s]

# Air drag coeff
RHO = 1.225 # kg/m^3
CD = 0.7
A = 7.5 # m^2
WEIGTH_VEH = 40000 # kg 

class VehicleState:
    """
    vehicle state class
    """
    def __init__(self, x=0.0, v=0.0):
        self.x = x
        self.v = v


def update_states(veh_states, control_signals):
    # updates states for all vehicles
    ''' Får ingen översläng när air drag läggs till och det blir även fel ibland med splittningen. Dvs splittningen påbörjar och sedan måste 
    komma till baka till start positionen för att den fattar efter ett tag att det inte går(t.ex. vid 60 meter). I det ideala fallet så blir 
    det en liten översläng och det blir aldirg fel med splittningen(påbörjas aldrig om den inte kan lösa det).
    '''
    
    # Ideal cond.
    for i in range(NUM_CARS):
        veh_states[i].x = veh_states[i].x + veh_states[i].v * DT
        veh_states[i].v = veh_states[i].v + control_signals[-NUM_CARS + i]* DT
    '''
    # Air drag cond.
    for i in range(NUM_CARS):
        if i != 0:
            CD_distance = CD * (1 - (13.41 / (23.53 + states[i-1].deltax))) # states ska bort byt till veh_states
            acc_ad = 0.5 * RHO * A * (veh_states[i].v * veh_states[i].v) * CD_distance / WEIGTH_VEH  # Air drag on vehicle i
            veh_states[i].v = veh_states[i].v + (control_signals[-NUM_CARS + i] - acc_ad) * DT
        else:
            veh_states[i].v = veh_states[i].v + control_signals[-NUM_CARS + i]* DT
        veh_states[i].x = veh_states[i].x + veh_states[i].v * DT 
    '''

    return veh_states
    

def mpc(veh_states, xref, split_car, last_ref_in_mpc, split_distance):
    """
    heavily inspired by https://www.cvxpy.org/tutorial/intro/index.html
    """
    Ad, Bd = create_matrices()
    
    # Cost matrices
    R = 1.0 * sparse.eye(NUM_CARS-1)

    q_vec = [0]*(2*NUM_CARS-1)
    # Kan även ha if satser i for loopen om man skulle vilja ha olika xref och Q beroende på vilken bil man vill splitta.
    for i in range(NUM_CARS):

        if i != NUM_CARS-1:
            q_vec[i] = 10.0
        q_vec[i+NUM_CARS-1] = 0.1
        if i == split_car-1:
                q_vec[i] = 3*10.0

    Q = sparse.diags(q_vec)
    QN = Q
    
    # Define a for loop here for mult. vehicles
    x0 = []
    for i in range(NUM_CARS-1):
        x0.append(veh_states[i].x - veh_states[i+1].x)
    for i in range(NUM_CARS):
        x0.append(veh_states[i].v)
    
    # Create two scalar optimization variables.
    u = cp.Variable((NUM_CARS-1, PREDICTION_HORIZON))
    x = cp.Variable((2*NUM_CARS-1, PREDICTION_HORIZON+1))
    # First constraints needs to be the initial state
    constraints = [x[:,0] == x0]
    # Define the cost function
    cost = 0.0

    for k in range(PREDICTION_HORIZON):
        cost += cp.quad_form(x[:,k] - xref, Q) + cp.quad_form(u[:,k], R)    # Add the cost function sum(x^TQx + u^TRu) 
        constraints += [x[:,k+1] == Ad@x[:,k] + Bd@u[:,k]]                  # Add the system x(k+1) = Ax(k) + Bu(k)
        for i in range(NUM_CARS):                                         # The for loop is for defining safety distance for all cars
            constraints += [MIN_VEL <= x[NUM_CARS-1+i,k], x[NUM_CARS-1+i,k] <= MAX_VEL]
            if i != NUM_CARS-1:
                constraints += [SAFETY_DISTANCE <= x[i,k]]
                if k >= (PREDICTION_HORIZON - last_ref_in_mpc):
                    constraints += [[split_distance + LENGTH] <= x[split_car-1,k]]  # -INTERVAL finns med för att skapa ett intervall

        constraints += [[MIN_ACCELERATION] <= u[:,k], u[:,k] <= [MAX_ACCELERATION]] # Constarints for the acc.


    cost += cp.quad_form(x[:,PREDICTION_HORIZON] - xref, QN)
    
    # Form and solve problem.
    prob = cp.Problem(cp.Minimize(cost), constraints)
    sol = prob.solve(solver=cp.ECOS)
    #print(u.value)
    return u[:,0].value


def create_matrices():

    # Define dimentions for A and B matrices
    A = np.zeros((2*NUM_CARS-1,2*NUM_CARS-1))
    B = np.zeros((2*NUM_CARS-1,(NUM_CARS-1)))

    for i in range(NUM_CARS-1):

        A[i,NUM_CARS-1+i] = 1
        A[i,NUM_CARS+i] = -1

        B[NUM_CARS+i,i] = 1

    # Identity matrix
    I = sparse.eye(2*NUM_CARS-1)

    # Discretize A and B matrices
    Ad = (I + DT*A)
    Bd =  DT*B
    return Ad, Bd


def plot_car(x, y=0.0, yaw=0.0, steer=0.0, cabcolor="-r", truckcolor="-k"):  # pragma: no cover
    '''Code from Author: Atsushi Sakai(@Atsushi_twi)'''
    outline = np.array([[-BACKTOWHEEL, (LENGTH - BACKTOWHEEL), (LENGTH - BACKTOWHEEL), -BACKTOWHEEL, -BACKTOWHEEL],
                        [WIDTH / 2, WIDTH / 2, - WIDTH / 2, -WIDTH / 2, WIDTH / 2]])

    fr_wheel = np.array([[WHEEL_LEN, -WHEEL_LEN, -WHEEL_LEN, WHEEL_LEN, WHEEL_LEN],
                         [-WHEEL_WIDTH - TREAD, -WHEEL_WIDTH - TREAD, WHEEL_WIDTH - TREAD, WHEEL_WIDTH - TREAD,
                          -WHEEL_WIDTH - TREAD]])

    rr_wheel = np.copy(fr_wheel)

    fl_wheel = np.copy(fr_wheel)
    fl_wheel[1, :] *= -1
    rl_wheel = np.copy(rr_wheel)
    rl_wheel[1, :] *= -1

    Rot1 = np.array([[math.cos(yaw), math.sin(yaw)],
                     [-math.sin(yaw), math.cos(yaw)]])
    Rot2 = np.array([[math.cos(steer), math.sin(steer)],
                     [-math.sin(steer), math.cos(steer)]])

    fr_wheel = (fr_wheel.T.dot(Rot2)).T
    fl_wheel = (fl_wheel.T.dot(Rot2)).T
    fr_wheel[0, :] += WB
    fl_wheel[0, :] += WB

    fr_wheel = (fr_wheel.T.dot(Rot1)).T
    fl_wheel = (fl_wheel.T.dot(Rot1)).T

    outline = (outline.T.dot(Rot1)).T
    rr_wheel = (rr_wheel.T.dot(Rot1)).T
    rl_wheel = (rl_wheel.T.dot(Rot1)).T

    outline[0, :] += x
    outline[1, :] += y
    fr_wheel[0, :] += x
    fr_wheel[1, :] += y
    rr_wheel[0, :] += x
    rr_wheel[1, :] += y
    fl_wheel[0, :] += x
    fl_wheel[1, :] += y
    rl_wheel[0, :] += x
    rl_wheel[1, :] += y

    plt.plot(np.array(outline[0, :]).flatten(),
             np.array(outline[1, :]).flatten(), truckcolor)
    plt.plot(np.array(fr_wheel[0, :]).flatten(),
             np.array(fr_wheel[1, :]).flatten(), truckcolor)
    plt.plot(np.array(rr_wheel[0, :]).flatten(),
             np.array(rr_wheel[1, :]).flatten(), truckcolor)
    plt.plot(np.array(fl_wheel[0, :]).flatten(),
             np.array(fl_wheel[1, :]).flatten(), truckcolor)
    plt.plot(np.array(rl_wheel[0, :]).flatten(),
             np.array(rl_wheel[1, :]).flatten(), truckcolor)
    plt.plot(x, y, "*")


def clear_and_draw_car(states):
    plt.cla()
    dl = 1  # course tick

    cx = []
    cy = []
    for i in range(ROAD_LENGTH):
        cx.append(i)
        cy.append(0)  # get the straight line

    plt.plot(cx, cy, "-r", label="course")
    for i in range(NUM_CARS):
        plot_car(states[i].x)  # plot the cars

    plt.axis([0, ROAD_LENGTH, -50, 50])
    plt.grid(True)
    plt.pause(0.0001)


def velocity_plotter(dt_list, v_list):
    plt.subplots(1)
    colors = ['-b', '-g', '-r', '-c', '-m', '-y', '-k']
    labels = ['v1', 'v2', 'v3', 'v4', 'v5', 'v6', 'v7']

    for i in range(NUM_CARS):
        plt.plot(dt_list, v_list[i::NUM_CARS], colors[i%7], label=('v' + str(i+1)))

    plt.grid(True)
    plt.axis("equal")
    plt.xlabel("time(s)")
    plt.ylabel("velocity")
    plt.legend()
    plt.show()


def acceleration_plotter(dt_list, u_list):
    plt.subplots(1)
    colors = ['-b', '-g', '-r', '-c', '-m', '-y', '-k']
    labels = ['a1', 'a2', 'a3', 'a4', 'a5', 'a6', 'a7']

    for i in range(NUM_CARS):
        plt.plot(dt_list, u_list[i::NUM_CARS], colors[i%7], label=('a' + str(i+1)))
    plt.grid(True)
    plt.axis("equal")
    plt.xlabel("time(s)")
    plt.ylabel("acceleration(m/s^2)")
    plt.legend()
    plt.show()


def distance_plotter(dt_list, distance_list):
    plt.subplots(1)
    colors = ['-b', '-g', '-r', '-c', '-m', '-y', '-k']
    labels = ['Δ12', 'Δ23', 'Δ34', 'Δ45', 'Δ56', 'Δ67']
    for i in range(NUM_CARS - 1):
        plt.plot(dt_list, distance_list[i::NUM_CARS - 1], colors[i%7], label=('Δ' + str(i+1) + str(i+2)))
    plt.grid(True)
    plt.axis('equal')
    plt.xlabel("time(s)")
    plt.ylabel("distance(m)")
    plt.legend()
    plt.show()


def position_plotter(dt_list, x_list):
    plt.subplots(1)
    colors = ['-b', '-g', '-r', '-c', '-m', '-y', '-k']
    labels = ['x1', 'x2', 'x3', 'x4', 'x5', 'x6', 'x7']

    for i in range(NUM_CARS):
        plt.plot(dt_list, x_list[i::NUM_CARS], colors[i%7], label=('x' + str(i+1)))
    plt.grid(True)
    plt.xlabel("time(s)")
    plt.ylabel("position(m)")
    plt.legend()
    plt.show()


def old_values_lists():
    ''' Define list to hold old values for plotting the graphs '''

    # Initial car positions
    x_list = []
    # Initial velocities
    v_list = []
    # Initial accelerations
    u_list = []
    for i in range(NUM_CARS):
        x_list.append(X_LIST[i])
        v_list.append(V_INIT)
        u_list.append(U_INIT)

    # Distance between the cars at the beginning
    distance_list = []
    for i in range(NUM_CARS - 1):
        distance_list.append(x_list[i] - x_list[i + 1] - LENGTH)

    # Time list
    dt_list = [0]

    return x_list, v_list, u_list, distance_list, dt_list


def renew_acc(u_list, try_split, next_control_signals):
    u_list.append(0)    # Leader acc. 0 -> vel. const
    for i in range(NUM_CARS-1):
        try:
            u_list.append(next_control_signals[i])
        except:
            u_list.append(0)
            if try_split == True:
                print('The split can not be accomplish. Cancelling the split.')
            try_split = False
    return u_list, try_split  


def renew_x_and_v(veh_states, x_list, v_list, distance_list):
    # Appends new states in position, velocity and acceleration list
    for i in range(NUM_CARS):
        v_list.append(veh_states[i].v)
        x_list.append(veh_states[i].x)

    for i in range(NUM_CARS - 1):
        distance_list.append(veh_states[i].x - veh_states[i+1].x - LENGTH)    
    
    return x_list, v_list, distance_list


def plot_graphs(v_list, distance_list, u_list, x_list, dt_list):
    # Creating plots for velocity, distance, acceleration and position
    velocity_plotter(dt_list, v_list)
    distance_plotter(dt_list, distance_list)
    acceleration_plotter(dt_list, u_list)
    position_plotter(dt_list, x_list)


def animation(inital_veh_states, split_event, initial_xref):
    '''Does the required calculations and plots the animation.'''

    # Defining initial states as the current states
    veh_states = inital_veh_states
    xref = initial_xref

    # Longitudial pos, velocity and acceleration lists. These hold the neccesary information for plotting
    x_list, v_list, u_list, distance_list, dt_list = old_values_lists()

    # Spliting condition
    split_car = int(split_event[0])
    split_distance = int(split_event[1])
    split_ready = float(split_event[2])

    # The simulation is done in this while-loop
    time = 0.0
    try_split = True
    while 5*MAX_TIME >= time:
        
        # Check if the prediction horizone can see the split position
        if (time + DT*PREDICTION_HORIZON) >= split_ready and try_split == True:
            last_ref_in_mpc = (time + PREDICTION_HORIZON * DT - split_ready)//DT +1     # How many of the last prediction horizone should have the hard constrain on the distance
            if time >= split_ready:
                xref[split_car-1] = split_distance + LENGTH     # Fix the reference for the car we want to split
        else:
            xref[split_car-1] = INIT_DIST + LENGTH #initial_xref[2*(split_car-1)]
            last_ref_in_mpc = -1     # None of the predictione horizone should have the distance as hard constrain
        
        next_control_signals = mpc(veh_states, xref, split_car, last_ref_in_mpc, split_distance)
        u_list, try_split = renew_acc(u_list, try_split, next_control_signals)  # Renew the acceleration list 
        clear_and_draw_car(veh_states)                                          # Draw the cars on the simulation
        veh_states = update_states(veh_states, u_list)          # Renew the vehicle states a for MPC
        x_list, v_list, distance_list = renew_x_and_v(veh_states, x_list, v_list, distance_list)

        # Updates time
        time += DT
        dt_list.append(time)

        # Breakes animation when first vehicle reaches goal
        if veh_states[0].x >= ROAD_LENGTH:
            break

    plot_graphs(v_list, distance_list, u_list, x_list, dt_list)


def pos_list_create():
    global NUM_CARS 
    global X_LIST

    NUM_CARS = int(input("Number of cars: "))
    X_POS = 0. # Initial position for the last car in the platoon
    
    X_LIST = [X_POS] 
    for i in range(NUM_CARS-1):
        X_POS += (INIT_DIST + LENGTH)
        X_LIST.append(X_POS) # Create a list where the cars position is written such as X_LIST = [0,10,20,..]
    X_LIST.reverse()   # Need to reverse the list so the first car in the platoon's position is at index 0. 
    return


def split_event_finder():
    # Taking input on where, how and when the split should occur
    split_event = []    
    split_event.append(input("Split behind vehicle: "))
    split_event.append(input("Split distance: "))
    split_event.append(input("Split end position give in time: "))
    return split_event


def main():
    pos_list_create()   # Create the initial position list and find how many vehicles the user wants to use

    initial_veh_states = [] # The current position and velocity for all the vehicles in the platoon
    initial_xref = [0]*(2*NUM_CARS-1)       # The reference states

    for i in range(NUM_CARS):
        initial_veh_states.append(VehicleState(X_LIST[i], V_INIT))
        initial_xref[NUM_CARS-1+i] = 0.0    # The velocity differnece at the beginning

    for i in range(NUM_CARS-1):
        initial_xref[i] = (initial_veh_states[i].x - initial_veh_states[i+1].x) # The distance betwenn the vehicles at the star

    split_event = split_event_finder()
    animation(initial_veh_states, split_event, initial_xref)


main()
