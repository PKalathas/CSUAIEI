abstract public class Human implements HumanInterface{
    private int health;         //values 0-100
    private int age;            //values 0-100
    private int strength;       //values 0-10
    private int hitTolerance;   //values 0-10
    private int intelligence;   //values 0-10

    public boolean equals(Object obj){
        if(obj == null) { return false; }
        if ( !( this.getClass().equals( obj.getClass() ) ) )
            return false;
        Human tmp = (Human) obj;

        return this.health == tmp.health &&
                this.age == tmp.age &&
                this.strength == tmp.strength &&
                this.hitTolerance == tmp.hitTolerance &&
                this.intelligence == tmp.intelligence;
    }
    Human(){
        this.health = 100;
        this.age = 18;
        this.strength = 3;
        this.hitTolerance = 2;
        this.intelligence = 2;
    }

    Human(int intelligence){
        this.health = 100;
        this.age = 18;
        this.strength = 3;
        this.hitTolerance = 2;
        this.intelligence = intelligence;
    }

    public void setHealth(int health) {
        this.health = health;
    }

    public void setAge(int age) {
        this.age = age;
    }

    public void setIntelligence(int intelligence) {
        this.intelligence = intelligence;
    }

    public void setHitTolerance(int hitTolerance) {
        this.hitTolerance = hitTolerance;
    }

    public void setStrength(int strength) {
        this.strength = strength;
    }

    public int getHealth() {
        return this.health;
    }

    public int getAge() {
        return this.age;
    }

    public int getHitTolerance() {
        return this.hitTolerance;
    }

    public int getIntelligence() {
        return this.intelligence;
    }

    public int getStrength() {
        return this.strength;
    }

    public double fight() {
        return this.getHealth() + this.getIntelligence() + this.getStrength() * this.getHitTolerance() / (double)this.getAge();
    }

    public void print() {
        System.out.println("Health:" + this.getHealth());
        System.out.println("Intelligence:" + this.getIntelligence());
        System.out.println("Strength:" + this.getStrength());
        System.out.println("Tolerance:" + this.getHitTolerance());
        System.out.println("Age:" + this.getAge());
    }
}
