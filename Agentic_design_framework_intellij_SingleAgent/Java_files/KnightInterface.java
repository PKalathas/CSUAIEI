public interface KnightInterface {

    public void setWeapon(int weapon);

    public int getWeapon();

    public double fight();

    default public void print() {
        System.out.println("Weapon:" + this.getWeapon());
    }

    default public int print(int x) {
        System.out.println("Weapon:" + this.getWeapon());
        return 0;
    }
}
