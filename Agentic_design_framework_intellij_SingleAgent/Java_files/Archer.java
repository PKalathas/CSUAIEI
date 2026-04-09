import java.awt.*;

public class Archer extends Human implements FighterInterface {

    int weapon; //value 1-5
    Point location = new Point();

    Archer() {
        super(6);
        this.weapon = 4;
        this.location.x = 3;
        this.location.y = 8;
    }

    public void setWeapon(int weapon) {
        this.weapon = weapon;
    }

    public int getWeapon() {
        return this.weapon;
    }

    public double fight() {
        return (super.fight() * this.getWeapon());
    }

    public void print() {
        super.print();
        System.out.println("Weapon:" + this.getWeapon());
        System.out.println("Location x:" + this.location.x);
        System.out.println("Location y:" + this.location.y);
    }
}
