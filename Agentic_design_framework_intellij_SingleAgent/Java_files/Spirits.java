abstract public class Spirits {
    private int wellBeing;
    private int radius;

    public void setWellBeing(int wellBeing){
        this.wellBeing = wellBeing;
    }

    public void setRadius(int radius){
        this.radius = radius;
    }

    public int getWellBeing(){
        return this.wellBeing;
    }

    public int getRadius(){
        return this.radius;
    }

    abstract public void interactionH(Human myHuman);
    abstract public void interactionC(Creature myCreature);
    abstract public void interactionA(Animal myAnimal);
}
