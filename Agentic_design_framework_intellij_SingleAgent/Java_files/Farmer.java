import java.awt.*;

public class Farmer extends Human implements FarmerInterface{

    int speed; //value 1-5
    Point location = new Point();

    Farmer(){
        super();
        this.speed = 4;
        this.location.x = 0;
        this.location.y = 0;
    }

    public void setSpeed(int speed){
        this.speed = speed;
    }

    public int getSpeed(){
        return this.speed;
    }

    public void run(){
        this.location.x = 5;
        this.location.y = 5;
    }

    public void print() {
        super.print();
        System.out.println("Speed:" + this.getSpeed());
        System.out.println("Location x:" + this.location.x);
        System.out.println("Location y:" + this.location.y);
    }

}
