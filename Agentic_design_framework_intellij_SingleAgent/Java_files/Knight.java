import java.awt.*;

public class Knight extends Human implements KnightInterface, FighterInterface, Comparable {

    int weapon; //value 1-5
    Point location = new Point();

    public int hashCode() {
        return ( 37 * weapon + 37 * location.x + 37 * location.y );
    }


    public int compareTo(Object o) {
        Knight tmp = (Knight) o;
        if ( this.weapon > tmp.weapon) { return 1; }
        else if ( this.weapon == tmp.weapon) { return 0; }
        else return -1;

        // return this.weapon - o.weapon;
    }

    public boolean equals(Object obj){
        if(obj == null) { return false; }
        if ( !( this.getClass().equals( obj.getClass() ) ) )
            return false;

        Knight tmp = (Knight) obj;

        return super.equals(tmp) &&
                this.weapon == tmp.weapon &&
                this.location.x == tmp.location.x &&
                this.location.y == tmp.location.y;
    }

    Knight() {
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
        KnightInterface.super.print();
        System.out.println("Location x:" + this.location.x);
        System.out.println("Location y:" + this.location.y);
    }

    public int print(int x) {
        FighterInterface.super.print(x);
        System.out.println("Location x:" + this.location.x);
        System.out.println("Location y:" + this.location.y);
        return x;
    }
}

